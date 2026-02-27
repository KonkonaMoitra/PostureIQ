/**
 * AI Interview Posture Analyser — script.js
 * Handles: dark mode, webcam stream, posture analysis, UI updates
 */

/* ── Dark Mode ─────────────────────────────────────────────────────────────── */
const DM_KEY = 'ipa-dark-mode';

function applyTheme(dark) {
  document.body.classList.toggle('light-mode', !dark);
  const btn = document.getElementById('dark-toggle');
  if (btn) btn.innerHTML = dark ? '☀️' : '🌙';
}

function initDarkMode() {
  const saved = localStorage.getItem(DM_KEY);
  const dark  = saved === null ? true : saved === 'true';
  applyTheme(dark);

  const btn = document.getElementById('dark-toggle');
  if (btn) {
    btn.addEventListener('click', () => {
      const isDark = !document.body.classList.contains('light-mode');
      applyTheme(!isDark);
      localStorage.setItem(DM_KEY, String(!isDark));
    });
  }
}

/* ── Auto-dismiss flash messages ──────────────────────────────────────────── */
function initFlash() {
  document.querySelectorAll('.flash-msg').forEach(el => {
    setTimeout(() => {
      el.style.opacity = '0';
      el.style.transform = 'translateX(20px)';
      el.style.transition = 'all 0.4s ease';
      setTimeout(() => el.remove(), 400);
    }, 4000);
  });
}

/* ── Webcam & Posture Detection ───────────────────────────────────────────── */
let stream      = null;
let isAnalysing = false;

async function startWebcam() {
  const video = document.getElementById('webcam-video');
  if (!video) return;

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' }
    });
    video.srcObject = stream;
    await video.play();

    const wrapper = document.getElementById('webcam-wrapper');
    if (wrapper) wrapper.classList.add('active');

    const statusEl = document.getElementById('cam-status');
    if (statusEl) {
      statusEl.textContent = 'CAMERA LIVE';
      statusEl.classList.add('live');
    }
  } catch (err) {
    showCamError('Camera access denied. Please allow camera permissions and refresh.');
    console.error('Webcam error:', err);
  }
}

function stopWebcam() {
  if (stream) {
    stream.getTracks().forEach(t => t.stop());
    stream = null;
  }
}

function captureFrame() {
  const video = document.getElementById('webcam-video');
  if (!video || !stream) return null;

  const canvas  = document.createElement('canvas');
  const quality = 0.6; // Compress: balance quality vs payload size
  const scale   = 0.75;

  canvas.width  = video.videoWidth  * scale;
  canvas.height = video.videoHeight * scale;

  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

  return canvas.toDataURL('image/jpeg', quality);
}

async function analysePosture() {
  if (isAnalysing) return;

  const imageData = captureFrame();
  if (!imageData) {
    showCamError('Please allow camera access first.');
    return;
  }

  setAnalysing(true);
  clearResults();

  try {
    const res = await fetch('/detect_posture', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ image: imageData }),
    });

    const data = await res.json();

    if (!res.ok || data.error) {
      showError(data.error || 'Analysis failed. Please try again.');
    } else {
      displayResults(data);
    }
  } catch (err) {
    showError('Network error. Check your connection and try again.');
    console.error('Analyse error:', err);
  } finally {
    setAnalysing(false);
  }
}

function setAnalysing(active) {
  isAnalysing = active;
  const btn     = document.getElementById('analyse-btn');
  const spinner = document.getElementById('btn-spinner');
  const btnText = document.getElementById('btn-text');

  if (!btn) return;

  btn.disabled = active;

  if (spinner) spinner.style.display = active ? 'inline-block' : 'none';
  if (btnText) btnText.textContent   = active ? 'Analysing…' : 'Analyse Posture';
}

function displayResults(data) {
  const panel = document.getElementById('results-panel');
  if (panel) panel.style.display = 'block';

  // Score ring
  updateScoreRing(data.posture_score);

  // Status badge
  const statusEl = document.getElementById('result-status');
  if (statusEl) {
    const cls = statusClass(data.posture_status);
    statusEl.innerHTML = `<span class="status-badge ${cls}">${data.posture_status}</span>`;
  }

  // Angles
  setAngle('angle-shoulder', data.shoulder_angle, '°');
  setAngle('angle-neck',     data.neck_angle,     '°');
  setAngle('angle-head',     data.head_tilt,      '°');
  setAngle('angle-spine',    data.spine_angle,    '°');

  // Confidence
  const confEl = document.getElementById('confidence-bar');
  if (confEl) {
    confEl.querySelector('.bar-fill').style.width = `${data.confidence}%`;
    const label = confEl.parentElement.querySelector('.conf-label');
    if (label) label.textContent = `${data.confidence}% detection confidence`;
  }

  // Feedback list
  const feedList = document.getElementById('feedback-list');
  if (feedList && data.feedback) {
    feedList.innerHTML = data.feedback.map(f => `
      <div class="feedback-item">
        <div class="feedback-icon">💡</div>
        <span>${f}</span>
      </div>
    `).join('');
  }

  // Overlay text on video
  const overlay = document.getElementById('overlay-score');
  if (overlay) {
    overlay.textContent = `${data.posture_score}/100 · ${data.posture_status}`;
    overlay.style.display = 'block';
  }

  // Scroll to results
  panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function updateScoreRing(score) {
  const ring   = document.getElementById('score-ring-fill');
  const numEl  = document.getElementById('score-number');
  if (!ring || !numEl) return;

  const r          = 50;
  const circumference = 2 * Math.PI * r;
  const offset     = circumference - (score / 100) * circumference;

  ring.style.strokeDasharray  = circumference;
  ring.style.strokeDashoffset = offset;
  ring.style.stroke           = scoreColor(score);

  numEl.textContent = score;
  numEl.style.color = scoreColor(score);
}

function setAngle(id, value, unit = '') {
  const el = document.getElementById(id);
  if (el) el.textContent = `${value}${unit}`;
}

function scoreColor(score) {
  if (score >= 85) return '#10b981';
  if (score >= 65) return '#3b82f6';
  if (score >= 45) return '#f59e0b';
  return '#ef4444';
}

function statusClass(status) {
  const map = {
    'Excellent':        'excellent',
    'Good':             'good',
    'Needs Improvement':'needs-imp',
    'Poor':             'poor',
  };
  return map[status] || 'good';
}

function clearResults() {
  const panel = document.getElementById('results-panel');
  if (panel) panel.style.display = 'none';
  const overlay = document.getElementById('overlay-score');
  if (overlay) overlay.style.display = 'none';
}

function showError(msg) {
  const el = document.getElementById('error-msg');
  if (el) { el.textContent = msg; el.style.display = 'block'; }
}

function showCamError(msg) {
  const el = document.getElementById('cam-error');
  if (el) { el.textContent = msg; el.style.display = 'block'; }
}

/* ── Dashboard Chart ──────────────────────────────────────────────────────── */
function initDashboardChart(labels, scores) {
  const canvas = document.getElementById('posture-chart');
  if (!canvas || typeof Chart === 'undefined') return;

  const gradient = canvas.getContext('2d').createLinearGradient(0, 0, 0, 260);
  gradient.addColorStop(0, 'rgba(59,130,246,0.25)');
  gradient.addColorStop(1, 'rgba(59,130,246,0)');

  new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label:           'Posture Score',
        data:            scores,
        borderColor:     '#3b82f6',
        backgroundColor: gradient,
        borderWidth:     2.5,
        pointBackgroundColor: '#3b82f6',
        pointRadius:     4,
        pointHoverRadius:7,
        fill:            true,
        tension:         0.4,
      }],
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      interaction:  { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(20,29,46,0.95)',
          borderColor:     '#1e2d45',
          borderWidth:     1,
          titleColor:      '#f1f5f9',
          bodyColor:       '#94a3b8',
          padding:         12,
          callbacks: {
            label: ctx => ` Score: ${ctx.parsed.y}/100`,
          },
        },
      },
      scales: {
        x: {
          grid:   { color: 'rgba(30,45,69,0.6)', drawBorder: false },
          ticks:  { color: '#475569', font: { size: 11 }, maxRotation: 30 },
          border: { display: false },
        },
        y: {
          min:    0,
          max:    100,
          grid:   { color: 'rgba(30,45,69,0.6)', drawBorder: false },
          ticks:  { color: '#475569', font: { size: 11 }, stepSize: 25 },
          border: { display: false },
        },
      },
    },
  });
}

/* ── Stop webcam on page unload ───────────────────────────────────────────── */
window.addEventListener('beforeunload', stopWebcam);
window.addEventListener('pagehide',     stopWebcam);

/* ── Init ─────────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  initDarkMode();
  initFlash();
});
