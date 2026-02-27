# PostureIQ — AI Interview Posture Analyser

Real-time interview posture detection using MediaPipe Pose. Scores your posture
0–100 based on geometric angle analysis of shoulders, neck, head, and spine.

---

## Project Structure

```
/AI Interview Posture Analyser
├── app.py                  ← Flask backend + posture analysis engine
├── requirements.txt
├── schema.sql              ← Database schema reference
├── /templates
│   ├── base.html           ← Navbar, flash messages, shared layout
│   ├── index.html          ← Landing page
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html      ← Analytics + Chart.js
│   └── posture.html        ← Webcam + live analysis
├── /static
│   ├── styles.css          ← Corporate dark theme (CSS variables)
│   └── script.js           ← Webcam, dark mode, Chart.js init
└── /database
    └── app.db              ← Auto-created by app.py on first run
```

---

## Setup & Run (Local)

### 1. Install Python 3.10+

### 2. Create virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set environment variables

```bash
# Linux / macOS
export SECRET_KEY="your-random-secret-key-here"

# Windows PowerShell
$env:SECRET_KEY = "your-random-secret-key-here"
```

### 5. Run the application

```bash
python app.py
```

Open `http://localhost:5000` in your browser.

> The database (`database/app.db`) is created automatically on first run.

---

## Posture Scoring

| Score | Status             | Criteria                              |
|-------|--------------------|---------------------------------------|
| 85–100| Excellent          | All angles within ideal thresholds    |
| 65–84 | Good               | Minor deviations, acceptable overall  |
| 45–64 | Needs Improvement  | One or more significant deviations    |
| 0–44  | Poor               | Multiple posture issues detected      |

### Measured Angles

| Metric          | Excellent | Acceptable | Needs Correction |
|-----------------|-----------|------------|-----------------|
| Shoulder slope  | < 5°      | 5–12°      | > 12°           |
| Neck tilt       | < 10°     | 10–20°     | > 20°           |
| Head tilt       | < 5°      | 5–10°      | > 10°           |
| Spine deviation | < 8°      | 8–15°      | > 15°           |

---

## Deployment (Production)

### Using Gunicorn (recommended)

```bash
pip install gunicorn
SECRET_KEY="your-secure-key" gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

### Using Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV SECRET_KEY="change-this-in-production"
EXPOSE 5000
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:app"]
```

### Important for production

- Set `SECRET_KEY` via environment variable (never hardcode)
- Use HTTPS (TLS termination via Nginx or a load balancer)
- Store `app.db` on a persistent volume if using containers
- Consider migrating to PostgreSQL for multi-user scale

---

## Security Features

- Password hashing via `werkzeug.security` (PBKDF2-SHA256)
- CSRF token on all POST forms (stored in server-side session)
- `login_required` decorator protects all analysis routes
- Rate limiting: 10 requests per 60 seconds per user
- No plaintext passwords stored
- Secret key via environment variable
- Input validation on all form fields
- Proper HTTP status codes throughout
