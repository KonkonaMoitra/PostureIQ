-- AI Interview Posture Analyser — Database Schema
-- Run: sqlite3 database/app.db < schema.sql

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    UNIQUE NOT NULL,
    email         TEXT    UNIQUE NOT NULL,
    password_hash TEXT    NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS posture_records (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    shoulder_angle REAL,       -- Deviation of shoulder line from horizontal (degrees)
    neck_angle     REAL,       -- Forward head tilt from vertical (degrees)
    head_tilt      REAL,       -- Left/right ear slope (degrees)
    spine_angle    REAL,       -- Spine deviation from vertical (degrees)
    posture_score  INTEGER,    -- Overall score 0–100
    posture_status TEXT,       -- Excellent / Good / Needs Improvement / Poor
    feedback       TEXT,       -- Semicolon-separated feedback strings
    confidence     REAL,       -- MediaPipe landmark visibility score (%)
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Index for fast user-specific queries
CREATE INDEX IF NOT EXISTS idx_posture_user ON posture_records(user_id, created_at DESC);
