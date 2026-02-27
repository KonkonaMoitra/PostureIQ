"""
AI Interview Posture Analyser
Flask backend with MediaPipe pose detection, SQLite storage, and secure authentication.
"""

import os
import sqlite3
import base64
import math
import secrets
import numpy as np
import json
import cv2
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify, g
)
from werkzeug.security import generate_password_hash, check_password_hash
import mediapipe as mp

# ─── App Configuration ──────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
DATABASE = os.path.join(os.path.dirname(__file__), "database", "app.db")

# ─── MediaPipe Setup ─────────────────────────────────────────────────────────
mp_pose = mp.solutions.pose
pose_detector = mp_pose.Pose(
    static_image_mode=False,
    model_complexity=1,
    enable_segmentation=False,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)

# ─── Database ────────────────────────────────────────────────────────────────
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    """Initialise database tables."""
    os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
    with app.app_context():
        db = get_db()
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                username     TEXT    UNIQUE NOT NULL,
                email        TEXT    UNIQUE NOT NULL,
                password_hash TEXT   NOT NULL,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS posture_records (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL,
                shoulder_angle REAL,
                neck_angle     REAL,
                head_tilt      REAL,
                spine_angle    REAL,
                posture_score  INTEGER,
                posture_status TEXT,
                feedback       TEXT,
                confidence     REAL,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            """
        )
        db.commit()


# ─── Auth Helpers ─────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def generate_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = generate_csrf_token


def validate_csrf(token):
    return token and token == session.get("csrf_token")


# ─── Rate Limiting (in-memory) ────────────────────────────────────────────────
_rate_store: dict = {}


def check_rate_limit(user_id: int, limit: int = 10, window: int = 60) -> bool:
    now = datetime.now().timestamp()
    if user_id not in _rate_store:
        _rate_store[user_id] = []
    _rate_store[user_id] = [t for t in _rate_store[user_id] if now - t < window]
    if len(_rate_store[user_id]) >= limit:
        return False
    _rate_store[user_id].append(now)
    return True


# ─── Posture Analysis Engine ──────────────────────────────────────────────────
def _angle_from_vertical(p1: list, p2: list) -> float:
    """Angle of the vector p1→p2 from the vertical axis, in degrees."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return abs(math.degrees(math.atan2(dx, -dy)))


def _slope_angle(p1: list, p2: list) -> float:
    """Horizontal slope angle between two points (deviation from flat), degrees."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    angle = abs(math.degrees(math.atan2(dy, dx)))
    if angle > 90:
        angle = 180 - angle
    return angle


def analyze_posture(image_b64: str) -> tuple:
    """
    Decode a base64 JPEG/PNG, run MediaPipe Pose, compute geometric angles,
    and return a dict of results or (None, error_string).
    """
   
    try:
        # ── Decode image ─────────────────────────────────────────────────────
        if "," in image_b64:
            image_b64 = image_b64.split(",", 1)[1]
        img_bytes = base64.b64decode(image_b64)
        np_arr = np.frombuffer(img_bytes, np.uint8)
        img_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if img_bgr is None:
            return None, "Could not decode image. Please try again."

        # ── Resize for performance ────────────────────────────────────────────
        img_bgr = cv2.resize(img_bgr, (640, 480))
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        # ── Run pose detection ────────────────────────────────────────────────
        results = pose_detector.process(img_rgb)
        if not results.pose_landmarks:
            return None, (
                "No person detected. Please ensure your full upper body is "
                "visible and the room is well lit."
            )

        lm = results.pose_landmarks.landmark
        h, w = img_bgr.shape[:2]

        def pt(idx: int) -> list:
            p = lm[idx]
            return [p.x * w, p.y * h]

        # ── Extract key landmarks ─────────────────────────────────────────────
        nose          = pt(mp_pose.PoseLandmark.NOSE.value)
        left_ear      = pt(mp_pose.PoseLandmark.LEFT_EAR.value)
        right_ear     = pt(mp_pose.PoseLandmark.RIGHT_EAR.value)
        left_shoulder = pt(mp_pose.PoseLandmark.LEFT_SHOULDER.value)
        right_shoulder= pt(mp_pose.PoseLandmark.RIGHT_SHOULDER.value)
        left_hip      = pt(mp_pose.PoseLandmark.LEFT_HIP.value)
        right_hip     = pt(mp_pose.PoseLandmark.RIGHT_HIP.value)

        mid_shoulder = [
            (left_shoulder[0] + right_shoulder[0]) / 2,
            (left_shoulder[1] + right_shoulder[1]) / 2,
        ]
        mid_hip = [
            (left_hip[0] + right_hip[0]) / 2,
            (left_hip[1] + right_hip[1]) / 2,
        ]
        mid_ear = [
            (left_ear[0] + right_ear[0]) / 2,
            (left_ear[1] + right_ear[1]) / 2,
        ]

        # ── Compute angles ────────────────────────────────────────────────────
        # 1. Shoulder slope (deviation from horizontal)
        shoulder_angle = _slope_angle(left_shoulder, right_shoulder)

        # 2. Neck / forward head posture (mid-ear to mid-shoulder from vertical)
        neck_angle = _angle_from_vertical(mid_shoulder, mid_ear)

        # 3. Head tilt left/right (ear slope)
        head_tilt = _slope_angle(left_ear, right_ear)

        # 4. Spine angle from vertical (mid-hip to mid-shoulder)
        spine_angle = _angle_from_vertical(mid_hip, mid_shoulder)

        # ── Confidence ────────────────────────────────────────────────────────
        weights = {
            mp_pose.PoseLandmark.LEFT_SHOULDER.value: 2,
            mp_pose.PoseLandmark.RIGHT_SHOULDER.value: 2,
            mp_pose.PoseLandmark.LEFT_HIP.value: 2,
            mp_pose.PoseLandmark.RIGHT_HIP.value: 2,
            mp_pose.PoseLandmark.LEFT_EAR.value: 1,
            mp_pose.PoseLandmark.RIGHT_EAR.value: 1,
            mp_pose.PoseLandmark.NOSE.value: 1,}

        total_weight = sum(weights.values())
        weighted_sum = sum(lm[i].visibility * weights[i] for i in weights)

        confidence = round((weighted_sum / total_weight) * 100, 1)
        # ── Scoring ───────────────────────────────────────────────────────────
        score = 100
        feedback: list[str] = []
        
        if confidence < 50:
            score -= 25
            feedback.append("Low detection confidence — ensure full upper body is visible.")


        # Shoulder levelness
        if shoulder_angle < 5:
            pass
        elif shoulder_angle < 12:
            score -= 10
            feedback.append("Slight shoulder imbalance — try to level both shoulders.")
        else:
            score -= 25
            feedback.append("Uneven shoulders detected — check your seating and straighten up.")

        # Neck forward tilt
        if neck_angle < 10:
            pass
        elif neck_angle < 20:
            score -= 15
            feedback.append("Mild forward head posture — draw your head back slightly.")
        else:
            score -= 30
            feedback.append(
                "Significant forward neck tilt — align your ears directly over your shoulders."
            )

        # Head tilt
        if head_tilt < 5:
            pass
        elif head_tilt < 10:
            score -= 5
            feedback.append("Slight head tilt — keep your head level for a confident look.")
        else:
            score -= 15
            feedback.append("Noticeable head tilt — straighten your head position.")

        # Spine / back straightness
        if spine_angle < 8:
            pass
        elif spine_angle < 15:
            score -= 10
            feedback.append("Mild slouching — sit up straight and engage your core.")
        else:
            score -= 25
            feedback.append(
                "Significant slouching detected — sit tall with your back against the chair."
            )

        score = max(0, min(100, score))

        if score >= 85:
            status = "Excellent"
        elif score >= 65:
            status = "Good"
        elif score >= 45:
            status = "Needs Improvement"
        else:
            status = "Poor"

        if not feedback:
            feedback.append(
                "Outstanding posture! You project confidence and professionalism."
            )

        return {
            "posture_score":  score,
            "posture_status": status,
            "shoulder_angle": round(shoulder_angle, 2),
            "neck_angle":     round(neck_angle, 2),
            "head_tilt":      round(head_tilt, 2),
            "spine_angle":    round(spine_angle, 2),
            "feedback":       feedback,
            "confidence":     confidence,
        }, None

    except Exception as exc:
        return None, f"Analysis error: {exc}"


# ─── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        if not validate_csrf(request.form.get("csrf_token")):
            flash("Invalid request token.", "danger")
            return redirect(url_for("register"))

        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")

        if not all([username, email, password, confirm]):
            flash("All fields are required.", "danger")
            return render_template("register.html")
        if len(username) < 3:
            flash("Username must be at least 3 characters.", "danger")
            return render_template("register.html")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("register.html")
        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")

        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, generate_password_hash(password)),
            )
            db.commit()
            flash("Account created! Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username or email already in use.", "danger")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        if not validate_csrf(request.form.get("csrf_token")):
            flash("Invalid request token.", "danger")
            return redirect(url_for("login"))

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        db   = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"]  = user["id"]
            session["username"] = user["username"]
            flash(f"Welcome back, {user['username']}!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    db      = get_db()
    user_id = session["user_id"]

    records = db.execute(
        "SELECT * FROM posture_records WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()

    total_sessions = len(records)
    avg_score = (
        round(sum(r["posture_score"] for r in records) / total_sessions, 1)
        if records else 0
    )
    latest = records[0] if records else None

    # Improvement from first to latest session
    improvement = 0
    if len(records) >= 2:
        first_score = records[-1]["posture_score"]
        last_score  = records[0]["posture_score"]
        if first_score > 0:
            improvement = round(((last_score - first_score) / first_score) * 100, 1)

    # Chart data — last 10 sessions chronologically
    chart_records = list(reversed(records[:10]))
    chart_labels  = [r["created_at"][:16] for r in chart_records]
    chart_scores  = [r["posture_score"] for r in chart_records]

    return render_template(
        "dashboard.html",
        total_sessions=total_sessions,
        avg_score=avg_score,
        latest=latest,
        improvement=improvement,
        chart_labels=chart_labels,
        chart_scores=chart_scores,
        records=records[:500],
    )


@app.route("/posture")
@login_required
def posture():
    return render_template("posture.html")


@app.route("/detect_posture", methods=["POST"])
@login_required
def detect_posture():
    user_id = session["user_id"]

    if not check_rate_limit(user_id):
        return jsonify({"error": "Rate limit exceeded. Please wait a moment."}), 429

    try:
        data = request.get_json(silent=True)
        if not data or "image" not in data:
            return jsonify({"error": "No image data provided."}), 400

        result, error = analyze_posture(data["image"])
        if error:
            return jsonify({"error": error}), 400

        # Persist record
        db = get_db()
        db.execute(
            """
            INSERT INTO posture_records
                (user_id, shoulder_angle, neck_angle, head_tilt, spine_angle,
                 posture_score, posture_status, feedback, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                result["shoulder_angle"],
                result["neck_angle"],
                result["head_tilt"],
                result["spine_angle"],
                result["posture_score"],
                result["posture_status"],
                "; ".join(result["feedback"]),
                result["confidence"],
            ),
        )
        db.commit()

        return jsonify(result), 200

    except Exception as exc:
        print(f"[detect_posture] Error: {exc}")
        return jsonify({"error": "Internal server error."}), 500

# ─── Downloadable Report Route ────────────────────────────────────────────────
@app.route("/report/<int:record_id>")
@login_required
def download_report(record_id):
    """Generate a plain-text posture report for a specific session."""
    db   = get_db()
    user_id = session["user_id"]

    record = db.execute(
        "SELECT * FROM posture_records WHERE id = ? AND user_id = ?",
        (record_id, user_id)
    ).fetchone()

    if not record:
        return "Report not found.", 404

    # Build a plain-text report
    report = f"""
POSTUREIQ — SESSION REPORT
===========================
User       : {session['username']}
Date       : {record['created_at']}
Session ID : {record['id']}

POSTURE SCORE
─────────────
Score      : {record['posture_score']} / 100
Status     : {record['posture_status']}
Confidence : {record['confidence']}%

ANGLE MEASUREMENTS
──────────────────
Shoulder Slope  : {record['shoulder_angle']}°
Neck Tilt       : {record['neck_angle']}°
Head Tilt       : {record['head_tilt']}°
Spine Angle     : {record['spine_angle']}°

FEEDBACK
────────
{record['feedback'].replace(';', chr(10))}

SCORING REFERENCE
─────────────────
85–100  Excellent        All angles within ideal thresholds
65–84   Good             Minor deviations, acceptable overall
45–64   Needs Improvement  One or more significant deviations
0–44    Poor             Multiple posture issues detected

Generated by PostureIQ · {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""

    from flask import Response
    return Response(
        report.strip(),
        mimetype="text/plain",
        headers={
            "Content-Disposition": f"attachment; filename=postureiq-report-{record_id}.txt"
        }
    )


# ─── Mock Interview Session Save Route ───────────────────────────────────────
@app.route("/mock_session", methods=["POST"])
@login_required
def mock_session():
    """
    Receives a list of posture scores from a timed mock session
    and saves the average as a single record.
    """
    try:
        data   = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Invalid request."}), 400
        scores = data.get("scores", [])

        if not scores or not isinstance(scores, list):
            return jsonify({"error": "No scores provided."}), 400

        avg_score = round(sum(scores) / len(scores))

        if avg_score >= 85:   status = "Excellent"
        elif avg_score >= 65: status = "Good"
        elif avg_score >= 45: status = "Needs Improvement"
        else:                 status = "Poor"

        db = get_db()
        db.execute(
            """
            INSERT INTO posture_records
                (user_id, posture_score, posture_status, feedback, confidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                avg_score,
                status,
                f"Mock interview session · {len(scores)} samples · avg score {avg_score}",
                100.0,
            ),
        )
        db.commit()

        return jsonify({"avg_score": avg_score, "status": status}), 200

    except Exception as exc:
        print(f"[mock_session] Error: {exc}")
        return jsonify({"error": "Internal server error."}), 500

# ─── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    # Use FLASK_DEBUG=1 environment variable instead of debug=True
    app.run(host="0.0.0.0", port=5000)
