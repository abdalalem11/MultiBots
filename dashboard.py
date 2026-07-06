"""
MultiBots Dashboard — password-protected monitoring web UI
==========================================================

A single-file Flask app that exposes:
  * A live HTML dashboard (auto-refreshing, no external JS/CSS deps).
  * A JSON REST API for programmatic control.
  * Per-bot log streaming.

Auth model
----------
* Single shared password (PBKDF2-HMAC-SHA256, 240k iterations, 24-byte salt).
* Login at ``/login`` → signed session cookie (HMAC, 12-hour TTL).
* CSRF token on every state-changing POST.
* Rate-limited login attempts (5 per minute per IP) to slow brute force.

The dashboard imports the running ``MultiBots`` instance from main.py
via ``dashboard.attach(multibots_instance)``. When run as a standalone
script for development, it builds its own throwaway MultiBots.

Routes
------
GET  /                  dashboard home (auth required)
GET  /login             login form
POST /login             authenticate
POST /logout            clear session
GET  /api/status        system + all-bot snapshot (JSON)
GET  /api/bots          list bot configs (env masked)
GET  /api/bots/<name>   single bot state
POST /api/bots/<name>/<action>   start | stop | restart | enable | disable
GET  /api/bots/<name>/logs?lines=200   tail of bot log buffer
GET  /api/metrics/history/<name>      per-bot CPU/RAM history (180 pts)
GET  /healthz           unauthenticated liveness probe (returns 200)
GET  /readyz            unauthenticated readiness probe (200 if config loaded)
"""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import logging
import os
import secrets
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from flask import (
    Flask, Response, abort, jsonify, make_response, redirect,
    render_template_string, request, session,
)

# Allow running both as a module and as a script.
try:
    from main import (  # type: ignore
        DEFAULTS, BotSupervisor, ConfigLoader, GracefulShutdown,
        KeepAlivePinger, MetricsCollector, MultiBots, WebhookNotifier,
        setup_logging, utc_now_iso,
    )
except ImportError:  # pragma: no cover — dev convenience
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from main import (  # type: ignore
        DEFAULTS, BotSupervisor, ConfigLoader, GracefulShutdown,
        KeepAlivePinger, MetricsCollector, MultiBots, WebhookNotifier,
        setup_logging, utc_now_iso,
    )

__version__ = "2.0.0"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SESSION_COOKIE = "mb_session"
CSRF_COOKIE = "mb_csrf"
SESSION_TTL = 12 * 3600          # 12 hours
LOGIN_RATE_LIMIT = 5             # attempts per minute per IP
LOGIN_RATE_WINDOW = 60.0
PBKDF2_ITERATIONS = 240_000
PBKDF2_SALT_BYTES = 24
PBKDF2_HASH_BYTES = 32

# ---------------------------------------------------------------------------
# Password hashing (PBKDF2-HMAC-SHA256)
# ---------------------------------------------------------------------------
def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """Return ``pbkdf2_sha256$<iter>$<salt_b64>$<hash_b64>``.

    The output format mirrors Django's so it's recognizable and easy to
    verify from any language. Use :func:`verify_password` to check.
    """
    import base64
    salt = salt or secrets.token_bytes(PBKDF2_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS, PBKDF2_HASH_BYTES,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check against a stored ``hash_password`` output."""
    import base64
    try:
        algo, iter_s, salt_b64, hash_b64 = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iter_s)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations, len(expected),
        )
        return hmac.compare_digest(expected, actual)
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Session signing (HMAC over cookie value)
# ---------------------------------------------------------------------------
class SessionSigner:
    """Tiny HMAC-based session signer — no external dep."""

    def __init__(self, secret: bytes):
        self.secret = secret

    def sign(self, payload: str) -> str:
        sig = hmac.new(self.secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{payload}.{sig}"

    def verify(self, signed: str, max_age: int = SESSION_TTL) -> bool:
        if not signed or "." not in signed:
            return False
        payload, sig = signed.rsplit(".", 1)
        expected = hmac.new(self.secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        # payload = "exp_timestamp:role"
        try:
            exp_s, _role = payload.split(":", 1)
            exp = int(exp_s)
        except (ValueError, TypeError):
            return False
        return time.time() < exp

    def issue(self, role: str = "admin", ttl: int = SESSION_TTL) -> str:
        exp = int(time.time()) + ttl
        return self.sign(f"{exp}:{role}")


# ---------------------------------------------------------------------------
# Rate limiter (in-memory, per-IP login throttle)
# ---------------------------------------------------------------------------
class LoginRateLimiter:
    def __init__(self) -> None:
        self._attempts: Dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, ip: str) -> bool:
        now = time.time()
        with self._lock:
            recent = [t for t in self._attempts[ip] if now - t < LOGIN_RATE_WINDOW]
            self._attempts[ip] = recent
            if len(recent) >= LOGIN_RATE_LIMIT:
                return False
            recent.append(now)
            return True


# ---------------------------------------------------------------------------
# HTML template — single string, no external CSS/JS
# ---------------------------------------------------------------------------
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MultiBots Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #0f1419; color: #c9d1d9; line-height: 1.5; padding: 20px;
  }
  .header {
    display: flex; justify-content: space-between; align-items: center;
    padding-bottom: 16px; border-bottom: 1px solid #21262d; margin-bottom: 20px;
  }
  .header h1 { font-size: 22px; color: #58a6ff; }
  .header .meta { font-size: 12px; color: #8b949e; }
  .grid { display: grid; gap: 16px; }
  .grid-3 { grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
  .grid-2 { grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); }
  .card {
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    padding: 16px;
  }
  .card h2 { font-size: 14px; color: #8b949e; text-transform: uppercase;
    margin-bottom: 12px; letter-spacing: 0.5px; }
  .stat { font-size: 28px; font-weight: 600; color: #f0f6fc; }
  .stat small { font-size: 13px; color: #8b949e; font-weight: 400; margin-left: 4px; }
  .stat-row { display: flex; justify-content: space-between; align-items: baseline;
    margin-bottom: 8px; font-size: 13px; }
  .stat-row .label { color: #8b949e; }
  .stat-row .value { color: #c9d1d9; font-variant-numeric: tabular-nums; }
  .bar { height: 6px; background: #21262d; border-radius: 3px; overflow: hidden; margin-top: 4px; }
  .bar > div { height: 100%; background: #58a6ff; transition: width 0.5s; }
  .bar > div.warn { background: #d29922; }
  .bar > div.crit { background: #f85149; }
  .bot-card { padding: 14px; }
  .bot-card h3 { font-size: 16px; margin-bottom: 4px; display: flex; align-items: center; gap: 8px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  .dot.running { background: #3fb950; }
  .dot.crashed { background: #f85149; }
  .dot.stopped { background: #8b949e; }
  .dot.starting, .dot.restarting { background: #d29922; }
  .dot.disabled { background: #6e7681; }
  .bot-meta { font-size: 12px; color: #8b949e; margin-bottom: 10px; }
  .actions { display: flex; gap: 6px; flex-wrap: wrap; }
  .btn {
    background: #21262d; border: 1px solid #30363d; color: #c9d1d9;
    padding: 5px 12px; border-radius: 5px; font-size: 12px; cursor: pointer;
    text-decoration: none; transition: background 0.15s;
  }
  .btn:hover { background: #30363d; }
  .btn.danger { color: #f85149; }
  .btn.success { color: #3fb950; }
  .log {
    background: #0d1117; border: 1px solid #21262d; border-radius: 6px;
    padding: 10px; font-family: "SF Mono", Monaco, Consolas, monospace;
    font-size: 11px; max-height: 320px; overflow-y: auto; white-space: pre-wrap;
    word-break: break-all;
  }
  .footer { margin-top: 24px; text-align: center; color: #6e7681; font-size: 11px; }
  .footer a { color: #58a6ff; text-decoration: none; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #21262d; }
  th { color: #8b949e; font-weight: 500; text-transform: uppercase; font-size: 11px; }
  .badge {
    display: inline-block; padding: 2px 8px; border-radius: 10px;
    font-size: 11px; font-weight: 500;
  }
  .badge.running { background: #1a3a2a; color: #3fb950; }
  .badge.crashed { background: #3a1a1a; color: #f85149; }
  .badge.stopped { background: #21262d; color: #8b949e; }
  .badge.starting, .badge.restarting { background: #3a2e1a; color: #d29922; }
  .badge.disabled { background: #21262d; color: #6e7681; }
</style>
</head>
<body>
<div class="header">
  <h1>⚡ MultiBots Dashboard</h1>
  <div class="meta">
    v{{ version }} · <span id="clock">{{ now }}</span> ·
    <a href="/logout" class="btn">Logout</a>
  </div>
</div>

<div class="grid grid-3">
  <div class="card"><h2>CPU</h2>
    <div class="stat">{{ sys.cpu_percent|round(1) }}<small>%</small></div>
    <div class="stat-row"><span class="label">Load (1/5/15m)</span>
      <span class="value">{{ sys.load_1|round(2) }} / {{ sys.load_5|round(2) }} / {{ sys.load_15|round(2) }}</span></div>
    <div class="stat-row"><span class="label">Cores</span><span class="value">{{ sys.cpu_count }}</span></div>
    <div class="bar"><div style="width: {{ sys.cpu_percent }}%" class="{{ 'crit' if sys.cpu_percent > 85 else ('warn' if sys.cpu_percent > 60 else '') }}"></div></div>
  </div>
  <div class="card"><h2>Memory</h2>
    <div class="stat">{{ sys.mem_used_mb|round(0) }}<small>/ {{ sys.mem_total_mb|round(0) }} MB</small></div>
    <div class="stat-row"><span class="label">Used</span><span class="value">{{ sys.mem_percent }}%</span></div>
    <div class="bar"><div style="width: {{ sys.mem_percent }}%" class="{{ 'crit' if sys.mem_percent > 85 else ('warn' if sys.mem_percent > 70 else '') }}"></div></div>
  </div>
  <div class="card"><h2>Disk & Processes</h2>
    <div class="stat-row"><span class="label">Disk used</span><span class="value">{{ sys.disk_percent }}%</span></div>
    <div class="bar"><div style="width: {{ sys.disk_percent }}%"></div></div>
    <div class="stat-row" style="margin-top:8px"><span class="label">Swap</span><span class="value">{{ sys.swap_used_mb|round(0) }} / {{ sys.swap_total_mb|round(0) }} MB ({{ sys.swap_percent }}%)</span></div>
    <div class="stat-row"><span class="label">Processes</span><span class="value">{{ sys.process_count }}</span></div>
    <div class="stat-row"><span class="label">Uptime</span><span class="value">{{ uptime_h }}h {{ uptime_m }}m</span></div>
  </div>
</div>

<h2 style="margin: 24px 0 12px; font-size: 16px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px;">Bots ({{ bots|length }})</h2>
<div class="grid grid-2">
{% for b in bots %}
  <div class="card bot-card">
    <h3><span class="dot {{ b.status }}"></span>{{ b.name }}
      <span class="badge {{ b.status }}">{{ b.status }}</span></h3>
    <div class="bot-meta">
      PID {{ b.pid or '—' }} · uptime {{ b.uptime_s }}s · restarts {{ b.restart_count }}
      {% if b.last_exit_code is not none %} · exit {{ b.last_exit_code }}{% endif %}
    </div>
    <div class="stat-row"><span class="label">CPU</span><span class="value">{{ b.cpu_percent }}%</span></div>
    <div class="stat-row"><span class="label">Memory</span><span class="value">{{ b.memory_mb }} MB</span></div>
    {% if b.last_error %}<div class="stat-row"><span class="label">Last error</span>
      <span class="value" style="color:#f85149">{{ b.last_error }}</span></div>{% endif %}
    <div class="actions" style="margin-top: 8px;">
      <button class="btn success" onclick="act('{{ b.name }}','start')">Start</button>
      <button class="btn" onclick="act('{{ b.name }}','restart')">Restart</button>
      <button class="btn danger" onclick="act('{{ b.name }}','stop')">Stop</button>
      <a class="btn" href="/api/bots/{{ b.name }}/logs?lines=120" target="_blank">Logs</a>
    </div>
  </div>
{% endfor %}
</div>

<h2 style="margin: 24px 0 12px; font-size: 16px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px;">Supervisor Log (live)</h2>
<div class="card">
  <div class="log" id="logbox">Loading…</div>
</div>

<div class="footer">
  MultiBots v{{ version }} · <a href="/api/status">/api/status</a> ·
  <a href="/healthz">/healthz</a> · auto-refresh 5s
</div>

<script>
const csrf = "{{ csrf_token }}";
function act(name, action) {
  if (!confirm(name + ' → ' + action + '?')) return;
  fetch('/api/bots/' + name + '/' + action, {
    method: 'POST', headers: {'X-CSRF-Token': csrf}
  }).then(r => r.json()).then(j => {
    alert(j.ok ? (action + ' OK') : ('Error: ' + (j.error || 'unknown')));
    location.reload();
  }).catch(e => alert('Request failed: ' + e));
}
function refresh() {
  fetch('/api/supervisor_log?lines=80').then(r => r.text()).then(t => {
    document.getElementById('logbox').textContent = t;
  }).catch(()=>{});
}
refresh();
setInterval(refresh, 5000);
// Update clock + reload page every 30s for fresh stats
setInterval(() => location.reload(), 30000);
</script>
</body>
</html>
"""


LOGIN_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MultiBots Login</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0f1419; color: #c9d1d9; display: flex; align-items: center;
    justify-content: center; min-height: 100vh; margin: 0; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 10px;
    padding: 32px; width: 100%; max-width: 360px; }
  h1 { color: #58a6ff; font-size: 22px; margin-bottom: 6px; }
  p.sub { color: #8b949e; font-size: 13px; margin-bottom: 22px; }
  label { display: block; font-size: 13px; color: #8b949e; margin-bottom: 6px; }
  input { width: 100%; padding: 9px 12px; background: #0d1117; border: 1px solid #30363d;
    border-radius: 6px; color: #c9d1d9; font-size: 14px; margin-bottom: 16px; }
  input:focus { outline: none; border-color: #58a6ff; }
  button { width: 100%; padding: 10px; background: #238636; color: white; border: none;
    border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer; }
  button:hover { background: #2ea043; }
  .err { color: #f85149; font-size: 13px; margin-bottom: 12px; }
</style></head>
<body>
<form class="card" method="post" action="/login">
  <h1>⚡ MultiBots</h1>
  <p class="sub">Sign in to access the dashboard</p>
  {% if error %}<div class="err">{{ error }}</div>{% endif %}
  <label for="pw">Password</label>
  <input type="password" id="pw" name="password" autofocus required>
  <button type="submit">Sign in</button>
</form>
</body></html>
"""


# ---------------------------------------------------------------------------
# Flask app factory
# ---------------------------------------------------------------------------
class DashboardApp:
    """Wraps the Flask app + auth wiring + rate limiter.

    Use :meth:`attach` to connect a running :class:`MultiBots` instance,
    then :meth:`run` to serve (or mount ``app`` under a WSGI server).
    """

    def __init__(self, settings: Optional[Dict[str, Any]] = None,
                 dashboard_cfg: Optional[Dict[str, Any]] = None):
        self.settings = settings or dict(DEFAULTS)
        # Merge dashboard config from config.json's _dashboard key.
        # Precedence (highest first): env vars > _dashboard key > defaults.
        if dashboard_cfg:
            for k, v in dashboard_cfg.items():
                if k.startswith("_"):
                    continue
                env_key = {
                    "password_hash": "dashboard_password_hash",
                    "session_secret": "dashboard_session_secret",
                }.get(k, k)
                # Only apply if env var hasn't already set it.
                if not self.settings.get(env_key):
                    self.settings[env_key] = v
        self.app = Flask(__name__)
        self.app.url_map.strict_slashes = False
        self.app.secret_key = (
            self.settings.get("dashboard_session_secret")
            or secrets.token_hex(32)
        )
        self.signer = SessionSigner(self.app.secret_key.encode("utf-8"))
        self.rate_limiter = LoginRateLimiter()
        self._mb: Optional[MultiBots] = None
        self._supervisor_log: list = []
        self._supervisor_log_lock = threading.Lock()
        self.log = logging.getLogger("multibots.dashboard")
        self._install_logging_hook()
        self._password_hash = self._resolve_password_hash()
        self._register_routes()

    # ---- wiring ----------------------------------------------------------
    def attach(self, mb: MultiBots) -> None:
        """Connect a running MultiBots instance (must already be started)."""
        self._mb = mb
        self.log.info("Dashboard attached to MultiBots (bots=%d)", len(mb.bots))

    def _resolve_password_hash(self) -> str:
        """Pick the password hash from (in order): env, config, or autogen."""
        h = self.settings.get("dashboard_password_hash") or ""
        if h:
            return h
        # No password configured — auto-generate one, print it once,
        # store on disk so it survives restarts (best effort).
        generated = _auto_generate_password()
        self.log.warning(
            "No dashboard password configured. Generated: %s", generated,
        )
        config_dir = os.path.dirname(self.settings.get("config_path", "config.json")) or "."
        persist_path = os.path.join(config_dir, ".multibots_dashboard_pw")
        try:
            with open(persist_path, "w", encoding="utf-8") as fh:
                fh.write(hash_password(generated))
            self.log.info("Persisted password hash to %s", persist_path)
            with open(persist_path, "r", encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError:
            # Read-only fs — keep hash in memory only.
            return hash_password(generated)

    def _install_logging_hook(self) -> None:
        """Capture the last N supervisor log lines for the dashboard.

        Uses a re-entrant lock (RLock) so that if the format/emit path
        itself triggers a log call (e.g. via a stream handler that
        writes to stdout which is redirected), we don't deadlock.
        """
        class _Capture(logging.Handler):
            def __init__(self, buf, lock):
                super().__init__()
                self.buf = buf
                self.lock = lock

            def emit(self, record):
                try:
                    line = self.format(record)
                    # Non-blocking: if the lock is already held (e.g.
                    # during a re-entrant log call), skip this line
                    # rather than deadlock.
                    if self.lock.acquire(blocking=False):
                        try:
                            self.buf.append(line)
                            # Keep buffer at ~2000 lines (trim to 1500 when full).
                            if len(self.buf) > 2000:
                                del self.buf[:500]
                        finally:
                            self.lock.release()
                except Exception:  # noqa: BLE001
                    pass

        # Replace the plain Lock with an RLock for safety.
        self._supervisor_log_lock = threading.RLock()
        h = _Capture(self._supervisor_log, self._supervisor_log_lock)
        h.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
            "%H:%M:%S",
        ))
        logging.getLogger("multibots").addHandler(h)

    # ---- auth helpers ----------------------------------------------------
    def _is_authed(self) -> bool:
        signed = request.cookies.get(SESSION_COOKIE) or session.get("sid") or ""
        return bool(signed) and self.signer.verify(signed)

    def _csrf_token(self) -> str:
        tok = session.get(CSRF_COOKIE)
        if not tok:
            tok = secrets.token_hex(16)
            session[CSRF_COOKIE] = tok
        return tok

    def _require_auth(self) -> Optional[Response]:
        if self._is_authed():
            return None
        return redirect("/login?next=" + (request.path or "/"))

    def _require_csrf(self) -> Optional[Response]:
        tok = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
        if tok and hmac.compare_digest(tok, session.get(CSRF_COOKIE, "")):
            return None
        return jsonify({"ok": False, "error": "invalid CSRF token"}), 403

    def _client_ip(self) -> str:
        # Honour one level of X-Forwarded-For (set by Render/Heroku/etc).
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()
        return request.remote_addr or "?"

    # ---- route registration ---------------------------------------------
    def _register_routes(self) -> None:

        @self.app.route("/healthz")
        def healthz():
            return Response("ok\n", mimetype="text/plain")

        @self.app.route("/readyz")
        def readyz():
            if self._mb and self._mb.supervisor is not None:
                return Response("ready\n", mimetype="text/plain")
            return Response("not ready\n", status=503, mimetype="text/plain")

        @self.app.route("/login", methods=["GET", "POST"])
        def login():
            if request.method == "GET":
                return render_template_string(LOGIN_HTML, error=None)
            ip = self._client_ip()
            if not self.rate_limiter.allow(ip):
                return render_template_string(
                    LOGIN_HTML,
                    error="Too many attempts. Wait a minute and try again.",
                ), 429
            pw = request.form.get("password", "")
            if not verify_password(pw, self._password_hash):
                return render_template_string(
                    LOGIN_HTML, error="Incorrect password.",
                ), 401
            sid = self.signer.issue(role="admin")
            resp = make_response(redirect(request.args.get("next") or "/"))
            resp.set_cookie(
                SESSION_COOKIE, sid, max_age=SESSION_TTL,
                httponly=True, samesite="Lax", secure=request.is_secure,
            )
            session["sid"] = sid
            return resp

        @self.app.route("/logout", methods=["GET", "POST"])
        def logout():
            session.clear()
            resp = make_response(redirect("/login"))
            resp.delete_cookie(SESSION_COOKIE)
            return resp

        @self.app.route("/")
        def index():
            auth = self._require_auth()
            if auth:
                return auth
            return self._render_dashboard()

        # ---- REST API ----------------------------------------------------
        @self.app.route("/api/status")
        def api_status():
            auth = self._require_auth()
            if auth:
                return auth
            return jsonify(self._status_snapshot())

        @self.app.route("/api/bots")
        def api_bots():
            auth = self._require_auth()
            if auth:
                return auth
            if not self._mb or not self._mb.supervisor:
                return jsonify([])
            return jsonify([s.to_public_dict()
                            for s in self._mb.supervisor.states.values()])

        @self.app.route("/api/bots/<name>")
        def api_bot(name):
            auth = self._require_auth()
            if auth:
                return auth
            if not self._mb or not self._mb.supervisor:
                return jsonify({"error": "supervisor not ready"}), 503
            state = self._mb.supervisor.states.get(name)
            if not state:
                return jsonify({"error": "unknown bot"}), 404
            return jsonify(state.to_public_dict())

        @self.app.route("/api/bots/<name>/<action>", methods=["POST"])
        def api_bot_action(name, action):
            auth = self._require_auth()
            if auth:
                return auth
            csrf = self._require_csrf()
            if csrf:
                return csrf
            if not self._mb or not self._mb.supervisor:
                return jsonify({"ok": False, "error": "supervisor not ready"}), 503
            sup = self._mb.supervisor
            actions = {
                "start": sup.start, "stop": sup.stop,
                "restart": sup.restart, "enable": sup.enable,
                "disable": sup.disable,
            }
            fn = actions.get(action)
            if not fn:
                return jsonify({"ok": False, "error": f"unknown action {action}"}), 400
            if name not in sup.bots:
                return jsonify({"ok": False, "error": "unknown bot"}), 404
            try:
                ok = fn(name)
                return jsonify({"ok": ok, "action": action, "bot": name})
            except Exception as exc:  # noqa: BLE001
                return jsonify({"ok": False, "error": str(exc)}), 500

        @self.app.route("/api/bots/<name>/logs")
        def api_bot_logs(name):
            auth = self._require_auth()
            if auth:
                return auth
            if not self._mb or not self._mb.supervisor:
                return Response("", mimetype="text/plain")
            if name not in self._mb.supervisor.bots:
                abort(404)
            lines = max(10, min(2000, int(request.args.get("lines", 200))))
            buf = self._captured_bot_lines(name, lines)
            return Response("\n".join(buf), mimetype="text/plain")

        @self.app.route("/api/supervisor_log")
        def api_supervisor_log():
            auth = self._require_auth()
            if auth:
                return auth
            lines = max(10, min(2000, int(request.args.get("lines", 100))))
            with self._supervisor_log_lock:
                buf = list(self._supervisor_log[-lines:])
            return Response("\n".join(buf), mimetype="text/plain")

        @self.app.route("/api/metrics/history/<name>")
        def api_metrics_history(name):
            auth = self._require_auth()
            if auth:
                return auth
            if not self._mb or not self._mb.supervisor:
                return jsonify([])
            state = self._mb.supervisor.states.get(name)
            if not state:
                return jsonify({"error": "unknown bot"}), 404
            return jsonify(list(state.history))

    # ---- helpers ---------------------------------------------------------
    def _captured_bot_lines(self, name: str, lines: int) -> list:
        """Pull recent lines tagged with the bot's logger name."""
        # We don't store per-bot log buffers separately — extract from the
        # supervisor capture (saves memory; dashboard is best-effort).
        prefix = f"[multibots.bot.{name}]"
        with self._supervisor_log_lock:
            matched = [l for l in self._supervisor_log if prefix in l]
        return matched[-lines:]

    def _status_snapshot(self) -> Dict[str, Any]:
        snap: Dict[str, Any] = {
            "ts": utc_now_iso(),
            "version": __version__,
            "system": {},
            "bots": [],
        }
        if self._mb and self._mb.metrics and self._mb.supervisor:
            snap["system"] = self._mb.metrics.system_snapshot()
            snap["bots"] = [s.to_public_dict()
                            for s in self._mb.supervisor.states.values()]
        return snap

    def _render_dashboard(self) -> Response:
        if not self._mb or not self._mb.supervisor:
            return Response("Dashboard not attached.", status=503)
        sys = self._mb.metrics.system_snapshot() if self._mb.metrics else {}
        bots = [s.to_public_dict()
                for s in self._mb.supervisor.states.values()]
        boot = sys.get("boot_time", time.time())
        up_s = max(0, time.time() - boot)
        up_h = int(up_s // 3600); up_m = int((up_s % 3600) // 60)
        html_out = render_template_string(
            DASHBOARD_HTML,
            version=__version__,
            now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            sys=sys, bots=bots,
            uptime_h=up_h, uptime_m=up_m,
            csrf_token=self._csrf_token(),
        )
        return Response(html_out, mimetype="text/html")

    # ---- run -------------------------------------------------------------
    def run(self, host: Optional[str] = None, port: Optional[int] = None,
            **kwargs) -> None:
        """Convenience runner — for production prefer gunicorn."""
        host = host or self.settings["host"]
        port = port or self.settings["port"]
        self.app.run(host=host, port=port, **kwargs)


# ---------------------------------------------------------------------------
# Auto password generator
# ---------------------------------------------------------------------------
def _auto_generate_password() -> str:
    """Generate a memorable-but-strong password like ``atom-tango-72``."""
    import random
    words = [
        "atom", "tango", "river", "stone", "paper", "cloud", "storm",
        "lunar", "atlas", "ember", "frost", "ghost", "halo", "ivory",
        "jelly", "krill", "lemon", "mango", "ninja", "ocean", "pixel",
        "quark", "raven", "solar", "tiger", "umbra", "vapor", "whale",
    ]
    return f"{random.choice(words)}-{random.choice(words)}-{random.randint(10, 99)}"


# ---------------------------------------------------------------------------
# Main runner — used when running dashboard.py directly (dev / standalone)
# ---------------------------------------------------------------------------
def main() -> int:
    settings = dict(DEFAULTS)
    log = setup_logging(
        level=settings["log_level"],
        log_dir=settings["log_dir"],
    )
    mb = MultiBots(settings=settings)
    # Load config first so we can pass _dashboard settings to the dashboard.
    mb.load_config()

    # Create the dashboard and install its log capture handler BEFORE
    # starting bots — otherwise we miss all the bot startup logs.
    dash = DashboardApp(settings=settings, dashboard_cfg=mb.dashboard_cfg)
    dash.attach(mb)

    # Now start the supervisor (bots will log into the captured buffer).
    mb.start(run_pinger=True, install_signals=True)
    log.info("Starting dashboard on %s:%s", settings["host"], settings["port"])
    try:
        dash.run(use_reloader=False, threaded=True)
    except KeyboardInterrupt:
        mb.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
