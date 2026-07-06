#!/usr/bin/env python3
"""
Live smoke test — boots the real dashboard, exercises every endpoint
with curl-equivalent HTTP requests, then shuts down.

This is the "does it actually work in production?" test that complements
the unit/integration pytest suite.

Run:  python scripts/smoke_live.py
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# Use a temp dir for bots + config.
TMP = Path("/tmp/mb_smoke")
TMP.mkdir(exist_ok=True)
bots_dir = TMP / "bots"
bots_dir.mkdir(exist_ok=True)

# Create a fake bot that just runs forever.
(bots_dir / "smoke_bot").mkdir(exist_ok=True)
(bots_dir / "smoke_bot" / "main.py").write_text(
    "import os, time, sys\n"
    "print(f'smoke_bot pid={os.getpid()}', flush=True)\n"
    "while True: time.sleep(1)\n"
)

# Write config.json
config = {
    "_dashboard": {},
    "_global": {"max_restarts": 3},
    "smoke_bot": {
        "source": "https://github.com/x/smoke.git",
        "run": "main.py",
        "env": {"TOKEN": "super-secret-token-1234567890"},
        "enabled": True,
    },
}
(TMP / "config.json").write_text(json.dumps(config, indent=2))

# Start the dashboard as a subprocess on port 10099.
env = os.environ.copy()
env["MB_PORT"] = "10099"
env["MB_HOST"] = "127.0.0.1"
env["MB_BOTS_DIR"] = str(bots_dir)
env["MB_CONFIG_PATH"] = str(TMP / "config.json")
env["MB_LOG_DIR"] = str(TMP / "logs")
env["MB_DASHBOARD_PASSWORD_HASH"] = ""  # auto-generate
env["MB_DASHBOARD_SESSION_SECRET"] = "smoke-test-secret"
env["MB_PING_INTERVAL"] = "9999"  # disable
env["MB_START_DELAY"] = "0.2"
env["MB_WATCHDOG_INTERVAL"] = "1.0"

print("→ Starting dashboard on http://127.0.0.1:10099 ...", flush=True)
proc = subprocess.Popen(
    [sys.executable, str(REPO / "dashboard.py")],
    env=env, cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    text=True,
)

# Read stdout in a thread to capture the auto-generated password.
captured = []
def reader():
    for line in iter(proc.stdout.readline, ""):
        captured.append(line.rstrip())
        print(f"  [dashboard] {line.rstrip()}", flush=True)

t = threading.Thread(target=reader, daemon=True)
t.start()

# Wait for "Generated:" line.
password = None
deadline = time.time() + 15
while time.time() < deadline:
    for line in captured:
        if "Generated:" in line:
            password = line.split("Generated:", 1)[1].strip()
            break
    if password:
        break
    time.sleep(0.2)
    if proc.poll() is not None:
        print("✗ Dashboard process exited early!")
        sys.exit(1)

if not password:
    print("✗ Did not find generated password in dashboard output.")
    proc.terminate()
    proc.wait(timeout=5)
    sys.exit(1)

print(f"→ Auto-generated password: {password!r}", flush=True)

# Wait for server to be ready.
deadline = time.time() + 15
ready = False
while time.time() < deadline:
    try:
        r = requests.get("http://127.0.0.1:10099/healthz", timeout=1)
        if r.status_code == 200:
            ready = True
            break
    except requests.RequestException:
        time.sleep(0.3)

if not ready:
    print("✗ Dashboard did not become ready in 15s.")
    proc.terminate()
    proc.wait(timeout=5)
    sys.exit(1)

print("✓ /healthz returned 200", flush=True)

# Test 1: Unauthenticated access to / should redirect.
r = requests.get("http://127.0.0.1:10099/", allow_redirects=False)
assert r.status_code in (302, 401), f"expected 302/401, got {r.status_code}"
print(f"✓ Unauthenticated / → {r.status_code}", flush=True)

# Test 2: Wrong password.
r = requests.post("http://127.0.0.1:10099/login", data={"password": "wrong"},
                   allow_redirects=False)
assert r.status_code == 401
print("✓ Wrong password rejected (401)", flush=True)

# Test 3: Login with correct password.
session = requests.Session()
r = session.post("http://127.0.0.1:10099/login",
                  data={"password": password}, allow_redirects=False)
assert r.status_code == 302
print("✓ Correct password → 302 redirect to /", flush=True)

# Test 4: Authed dashboard.
r = session.get("http://127.0.0.1:10099/")
assert r.status_code == 200
assert "MultiBots Dashboard" in r.text
assert "smoke_bot" in r.text
print("✓ Authed / shows dashboard with smoke_bot", flush=True)

# Test 5: /api/status
r = session.get("http://127.0.0.1:10099/api/status")
assert r.status_code == 200
data = r.json()
assert "system" in data
assert "bots" in data
assert len(data["bots"]) == 1
assert data["bots"][0]["name"] == "smoke_bot"
print(f"✓ /api/status: 1 bot, status={data['bots'][0]['status']}", flush=True)

# Test 6: Token must NOT appear in the API response (masking).
assert "super-secret-token-1234567890" not in r.text
print("✓ TOKEN value masked in API response (no secret leak)", flush=True)

# Test 7: /api/bots/smoke_bot
r = session.get("http://127.0.0.1:10099/api/bots/smoke_bot")
assert r.status_code == 200
assert r.json()["status"] == "running"
print("✓ /api/bots/smoke_bot → running", flush=True)

# Test 8: Get CSRF token from dashboard HTML.
r = session.get("http://127.0.0.1:10099/")
import re
m = re.search(r'const csrf = "([^"]+)"', r.text)
assert m, "CSRF token not found"
csrf = m.group(1)
print(f"✓ CSRF token issued: {csrf[:8]}...", flush=True)

# Test 9: Restart via API (with CSRF).
r = session.post("http://127.0.0.1:10099/api/bots/smoke_bot/restart",
                  headers={"X-CSRF-Token": csrf})
assert r.status_code == 200
assert r.json()["ok"] is True
print("✓ POST /api/bots/smoke_bot/restart → ok", flush=True)

# Wait for it to come back up.
deadline = time.time() + 5
while time.time() < deadline:
    r = session.get("http://127.0.0.1:10099/api/bots/smoke_bot")
    if r.json()["status"] == "running":
        break
    time.sleep(0.2)
assert r.json()["status"] == "running"
print("✓ Bot back to running after restart", flush=True)

# Test 10: Stop via API.
r = session.post("http://127.0.0.1:10099/api/bots/smoke_bot/stop",
                  headers={"X-CSRF-Token": csrf})
assert r.status_code == 200
time.sleep(1.0)
r = session.get("http://127.0.0.1:10099/api/bots/smoke_bot")
assert r.json()["status"] == "stopped"
print("✓ Stop via API works", flush=True)

# Test 11: Start via API.
r = session.post("http://127.0.0.1:10099/api/bots/smoke_bot/start",
                  headers={"X-CSRF-Token": csrf})
assert r.status_code == 200
time.sleep(1.0)
r = session.get("http://127.0.0.1:10099/api/bots/smoke_bot")
assert r.json()["status"] == "running"
print("✓ Start via API works", flush=True)

# Test 12: /api/supervisor_log
r = session.get("http://127.0.0.1:10099/api/supervisor_log?lines=50")
assert r.status_code == 200
assert "smoke_bot" in r.text
print("✓ /api/supervisor_log contains bot name", flush=True)

# Test 13: /api/bots/smoke_bot/logs
r = session.get("http://127.0.0.1:10099/api/bots/smoke_bot/logs?lines=50")
assert r.status_code == 200
print("✓ /api/bots/smoke_bot/logs → text", flush=True)

# Test 14: /api/metrics/history/smoke_bot
r = session.get("http://127.0.0.1:10099/api/metrics/history/smoke_bot")
assert r.status_code == 200
assert isinstance(r.json(), list)
print(f"✓ /api/metrics/history/smoke_bot → {len(r.json())} samples", flush=True)

# Test 15: Logout.
r = session.post("http://127.0.0.1:10099/logout", allow_redirects=False)
assert r.status_code == 302
r = session.get("http://127.0.0.1:10099/", allow_redirects=False)
assert r.status_code in (302, 401)
print("✓ Logout clears session", flush=True)

# Test 16: Unknown bot 404.
session.post("http://127.0.0.1:10099/login", data={"password": password})
r = session.get("http://127.0.0.1:10099/api/bots/ghost")
assert r.status_code == 404
print("✓ Unknown bot → 404", flush=True)

# Test 17: Bad CSRF 403.
r = session.post("http://127.0.0.1:10099/api/bots/smoke_bot/stop",
                  headers={"X-CSRF-Token": "garbage"})
assert r.status_code == 403
print("✓ Bad CSRF → 403", flush=True)

print("\n========================================")
print("✅ ALL LIVE SMOKE TESTS PASSED")
print("========================================")

# Cleanup.
print("\n→ Shutting down dashboard via SIGTERM...", flush=True)
proc.send_signal(signal.SIGTERM)
try:
    proc.wait(timeout=10)
    print("✓ Dashboard shut down cleanly within 10s.", flush=True)
except subprocess.TimeoutExpired:
    print("✗ Dashboard didn't shut down in 10s — killing.", flush=True)
    proc.kill()
    proc.wait()
    sys.exit(1)
