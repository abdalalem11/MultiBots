#!/usr/bin/env python3
"""
MultiBots Enterprise Live Audit
================================

This is NOT a unit test. This script:

1. Boots a REAL MultiBots dashboard subprocess on port 10077.
2. Talks to it via real HTTP (curl-style requests).
3. Inspects real OS process state (psutil).
4. Sends real signals (SIGTERM, SIGKILL).
5. Verifies EVERY feature works end-to-end.

Total checks: ~50. Any failure is reported with full context.

Usage:
    python scripts/live_audit.py
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import shutil
from pathlib import Path

import psutil
import requests

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PORT = 10077
HOST = "127.0.0.1"
BASE = f"http://{HOST}:{PORT}"
TMP = Path("/tmp/mb_live_audit")
TMP.mkdir(exist_ok=True)
BOTS_DIR = TMP / "bots"
LOG_DIR = TMP / "logs"
CONFIG_PATH = TMP / "config.json"

# Clean previous run.
if BOTS_DIR.exists():
    shutil.rmtree(BOTS_DIR)
BOTS_DIR.mkdir(parents=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Fake bot scripts for different scenarios
# ---------------------------------------------------------------------------
def write_bot(name: str, script: str, run_file: str = "main.py"):
    d = BOTS_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    (d / run_file).write_text(script)
    return d

# A stable bot that prints startup info + heartbeat file, then sleeps forever.
STABLE_BOT = """
import os, sys, time
print(f'STABLE_BOT pid={os.getpid()} parent={os.getppid()}', flush=True)
with open('heartbeat.ok', 'w') as fh:
    fh.write(str(os.getpid()))
# Write env file so audit can verify env was passed correctly.
with open('env_dump.json', 'w') as fh:
    import json
    fh.write(json.dumps({k: os.environ.get(k) for k in os.environ if k in ('TOKEN','SECRET','DEBUG','PORT')}))
while True:
    time.sleep(1)
"""

# A bot that exits immediately with code 2.
CRASHY_BOT = """
import sys
print('CRASHY_BOT: exiting immediately with code 2', flush=True)
sys.exit(2)
"""

# A bot that ignores SIGTERM (to test SIGKILL fallback).
STUBBORN_BOT = """
import os, sys, signal, time
print(f'STUBBORN_BOT pid={os.getpid()}: ignoring SIGTERM', flush=True)
with open('pid.stubborn', 'w') as fh:
    fh.write(str(os.getpid()))
# Ignore SIGTERM entirely.
signal.signal(signal.SIGTERM, signal.SIG_IGN)
while True:
    time.sleep(1)
"""

# A bot that prints a lot of output (to test log drainage).
VERBOSE_BOT = """
import os, sys, time
print(f'VERBOSE_BOT pid={os.getpid()}: starting spam', flush=True)
i = 0
while True:
    print(f'VERBOSE_BOT line {i}', flush=True)
    i += 1
    time.sleep(0.1)
"""

# A bot that takes args.
ARGV_BOT = """
import sys, os, time
print(f'ARGV_BOT args={sys.argv[1:]}', flush=True)
with open('args_dump.json', 'w') as fh:
    import json
    fh.write(json.dumps(sys.argv[1:]))
while True:
    time.sleep(1)
"""

# Create all fake bots.
write_bot("stable_bot", STABLE_BOT)
write_bot("crashy_bot", CRASHY_BOT)
write_bot("stubborn_bot", STUBBORN_BOT)
write_bot("verbose_bot", VERBOSE_BOT)
write_bot("argv_bot", ARGV_BOT)
# disabled_bot — we'll set enabled=false in config so it never starts
write_bot("disabled_bot", STABLE_BOT)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CONFIG = {
    "_dashboard": {
        # We'll set the password hash after generating it.
    },
    "_global": {
        "max_restarts": 5,
        "restart_delay_base": 0.5,
    },
    "stable_bot": {
        "source": "https://github.com/audit/stable.git",
        "run": "main.py",
        "env": {"TOKEN": "sk-stable-1234567890abcdef", "SECRET": "very-secret-value-xyz", "DEBUG": "true"},
        "enabled": True,
    },
    "crashy_bot": {
        "source": "https://github.com/audit/crashy.git",
        "run": "main.py",
        "env": {"TOKEN": "crashy-token"},
        "enabled": True,
        "max_restarts": 3,
        "restart_delay_base": 0.3,
    },
    "stubborn_bot": {
        "source": "https://github.com/audit/stubborn.git",
        "run": "main.py",
        "env": {"TOKEN": "stubborn-token"},
        "enabled": False,  # we'll enable via API later
    },
    "verbose_bot": {
        "source": "https://github.com/audit/verbose.git",
        "run": "main.py",
        "env": {"TOKEN": "verbose-token"},
        "enabled": True,
    },
    "argv_bot": {
        "source": "https://github.com/audit/argv.git",
        "run": "main.py",
        "env": {"TOKEN": "argv-token"},
        "enabled": True,
        "args": ["--workers", "4", "--debug", "--port", "8080"],
    },
    "disabled_bot": {
        "source": "https://github.com/audit/disabled.git",
        "run": "main.py",
        "env": {"TOKEN": "disabled-token"},
        "enabled": False,
    },
}

# Generate password hash.
sys.path.insert(0, str(REPO))
from dashboard import hash_password
PASSWORD = "audit-test-password-2026"
CONFIG["_dashboard"]["password_hash"] = hash_password(PASSWORD)
CONFIG["_dashboard"]["session_secret"] = "audit-secret-do-not-reuse"

CONFIG_PATH.write_text(json.dumps(CONFIG, indent=2))

# ---------------------------------------------------------------------------
# Audit infrastructure
# ---------------------------------------------------------------------------
PASS = 0
FAIL = 0
SKIPPED = 0
FAILURES = []

def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        FAILURES.append((name, detail))
        print(f"  ✗ {name} — {detail}")

def skip(name: str, reason: str = ""):
    global SKIPPED
    SKIPPED += 1
    print(f"  ⊘ {name} (skipped: {reason})")

def section(title: str):
    print(f"\n{'='*70}\n  {title}\n{'='*70}")

# ---------------------------------------------------------------------------
# Start the dashboard subprocess
# ---------------------------------------------------------------------------
section("BOOTING DASHBOARD SUBPROCESS")
env = os.environ.copy()
env.update({
    "MB_PORT": str(PORT),
    "MB_HOST": HOST,
    "MB_BOTS_DIR": str(BOTS_DIR),
    "MB_CONFIG_PATH": str(CONFIG_PATH),
    "MB_LOG_DIR": str(LOG_DIR),
    "MB_PING_INTERVAL": "9999",  # disable pinger
    "MB_START_DELAY": "0.3",
    "MB_WATCHDOG_INTERVAL": "0.5",
    "MB_METRICS_HISTORY": "60",
    "MB_DASHBOARD_SESSION_SECRET": "audit-secret-do-not-reuse",
})

print(f"  Starting: python dashboard.py (port {PORT})")
proc = subprocess.Popen(
    [sys.executable, str(REPO / "dashboard.py")],
    env=env, cwd=str(REPO),
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
)
output_lines = []
def reader():
    for line in iter(proc.stdout.readline, ""):
        output_lines.append(line.rstrip())
        # Only print critical lines to keep audit output readable.
        if "ERROR" in line or "CRITICAL" in line or "Generated:" in line or "Traceback" in line:
            print(f"    [dashboard] {line.rstrip()}")

threading.Thread(target=reader, daemon=True).start()

# Wait for /healthz to return 200.
deadline = time.time() + 20
booted = False
while time.time() < deadline:
    try:
        r = requests.get(f"{BASE}/healthz", timeout=1)
        if r.status_code == 200:
            booted = True
            break
    except requests.RequestException:
        pass
    if proc.poll() is not None:
        print(f"  ✗ Dashboard process exited early with code {proc.returncode}")
        print(f"    Last 30 output lines:")
        for l in output_lines[-30:]:
            print(f"    {l}")
        sys.exit(1)
    time.sleep(0.3)

check("Dashboard boots and /healthz returns 200", booted)
if not booted:
    print("\nFATAL: Dashboard did not boot. Aborting.")
    sys.exit(1)

# Wait a few seconds for bots to start.
time.sleep(3)

# ---------------------------------------------------------------------------
# SECTION 1: Public endpoints (no auth)
# ---------------------------------------------------------------------------
section("1. PUBLIC ENDPOINTS (no auth)")

r = requests.get(f"{BASE}/healthz", timeout=2)
check("/healthz returns 200", r.status_code == 200, f"got {r.status_code}")
check("/healthz returns 'ok'", r.text.strip() == "ok", f"got {r.text!r}")

r = requests.get(f"{BASE}/readyz", timeout=2)
check("/readyz returns 200 (supervisor attached)", r.status_code == 200, f"got {r.status_code}")

# Unauthenticated dashboard should redirect to /login.
r = requests.get(f"{BASE}/", allow_redirects=False, timeout=2)
check("Unauthenticated / redirects to /login",
      r.status_code == 302 and "/login" in r.headers.get("Location", ""),
      f"got {r.status_code}, Location={r.headers.get('Location')}")

# Unauthenticated API should also redirect or 401.
r = requests.get(f"{BASE}/api/status", allow_redirects=False, timeout=2)
check("Unauthenticated /api/status gated",
      r.status_code in (301, 302, 401, 403), f"got {r.status_code}")

# ---------------------------------------------------------------------------
# SECTION 2: Authentication
# ---------------------------------------------------------------------------
section("2. AUTHENTICATION")

# Wrong password.
r = requests.post(f"{BASE}/login", data={"password": "wrong"}, timeout=2)
check("Wrong password → 401", r.status_code == 401, f"got {r.status_code}")

# Empty password.
r = requests.post(f"{BASE}/login", data={"password": ""}, timeout=2)
check("Empty password → 401", r.status_code == 401, f"got {r.status_code}")

# Correct password.
s = requests.Session()
r = s.post(f"{BASE}/login", data={"password": PASSWORD}, allow_redirects=False, timeout=2)
check("Correct password → 302 redirect", r.status_code == 302, f"got {r.status_code}")
check("Redirect target is /", r.headers.get("Location", "").endswith("/"),
      f"Location={r.headers.get('Location')}")

# Verify session cookie is set.
cookies = s.cookies.get_dict()
check("Session cookie set", "mb_session" in cookies, f"cookies={list(cookies.keys())}")

# Authed dashboard now returns 200.
r = s.get(f"{BASE}/", timeout=2)
check("Authed / returns 200", r.status_code == 200, f"got {r.status_code}")
check("Dashboard HTML contains 'MultiBots Dashboard'", "MultiBots Dashboard" in r.text)
check("Dashboard HTML contains CSRF token", 'const csrf = "' in r.text)

# Extract CSRF token.
import re
m = re.search(r'const csrf = "([^"]+)"', r.text)
CSRF = m.group(1) if m else ""
check("CSRF token extracted", bool(CSRF), f"match={m}")

# Rate limit: 5 wrong attempts from a fresh session should get 429.
rs = requests.Session()
got_429 = False
for i in range(7):
    r = rs.post(f"{BASE}/login", data={"password": "bad"}, timeout=2)
    if r.status_code == 429:
        got_429 = True
        break
check("Rate limit kicks in (429 after 5 attempts)", got_429,
      f"never got 429, last status={r.status_code}")

# ---------------------------------------------------------------------------
# SECTION 3: Bots started correctly
# ---------------------------------------------------------------------------
section("3. BOT STARTUP (5 enabled bots)")

# Wait for stable_bot to come up.
deadline = time.time() + 10
stable_running = False
while time.time() < deadline:
    r = s.get(f"{BASE}/api/bots/stable_bot", timeout=2)
    if r.status_code == 200 and r.json().get("status") == "running":
        stable_running = True
        break
    time.sleep(0.3)
check("stable_bot reached 'running' state", stable_running)

# Verify heartbeat file was written (proves the bot actually executed).
hb = BOTS_DIR / "stable_bot" / "heartbeat.ok"
check("stable_bot wrote heartbeat.ok file", hb.exists())

# Verify env was passed to the bot.
env_dump = BOTS_DIR / "stable_bot" / "env_dump.json"
if env_dump.exists():
    env_data = json.loads(env_dump.read_text())
    check("stable_bot received TOKEN env", env_data.get("TOKEN") == "sk-stable-1234567890abcdef",
          f"got {env_data.get('TOKEN')!r}")
    check("stable_bot received SECRET env", env_data.get("SECRET") == "very-secret-value-xyz",
          f"got {env_data.get('SECRET')!r}")
    check("stable_bot received DEBUG env", env_data.get("DEBUG") == "true")
else:
    check("stable_bot env dump exists", False, "env_dump.json not written")

# Verify args were passed to argv_bot.
args_dump = BOTS_DIR / "argv_bot" / "args_dump.json"
deadline = time.time() + 5
while time.time() < deadline and not args_dump.exists():
    time.sleep(0.2)
if args_dump.exists():
    args_data = json.loads(args_dump.read_text())
    check("argv_bot received --workers 4", args_data == ["--workers", "4", "--debug", "--port", "8080"],
          f"got {args_data}")
else:
    check("argv_bot args dump exists", False, "args_dump.json not written")

# disabled_bot should be in "disabled" state.
r = s.get(f"{BASE}/api/bots/disabled_bot", timeout=2)
check("disabled_bot is in 'disabled' state",
      r.status_code == 200 and r.json().get("status") == "disabled",
      f"got status={r.json().get('status') if r.status_code == 200 else r.status_code}")

# stubborn_bot also disabled in config.
r = s.get(f"{BASE}/api/bots/stubborn_bot", timeout=2)
check("stubborn_bot is in 'disabled' state (config)",
      r.status_code == 200 and r.json().get("status") == "disabled")

# ---------------------------------------------------------------------------
# SECTION 4: API endpoint coverage
# ---------------------------------------------------------------------------
section("4. REST API COVERAGE")

# /api/status
r = s.get(f"{BASE}/api/status", timeout=2)
check("/api/status → 200", r.status_code == 200)
data = r.json()
check("/api/status has 'ts' field", "ts" in data)
check("/api/status has 'system' field", "system" in data)
check("/api/status has 'bots' field", "bots" in data)
check("/api/status bots count = 6", len(data["bots"]) == 6, f"got {len(data['bots'])}")

# System metrics sanity.
sys_snap = data["system"]
check("System has cpu_percent", "cpu_percent" in sys_snap and sys_snap["cpu_percent"] >= 0)
check("System has mem_percent (0-100)", 0 <= sys_snap.get("mem_percent", -1) <= 100)
check("System has disk_percent (0-100)", 0 <= sys_snap.get("disk_percent", -1) <= 100)
check("System has load_1", "load_1" in sys_snap)
check("System has cpu_count >= 1", sys_snap.get("cpu_count", 0) >= 1)
check("System has process_count", sys_snap.get("process_count", 0) > 0)

# /api/bots
r = s.get(f"{BASE}/api/bots", timeout=2)
check("/api/bots → 200", r.status_code == 200)
bots_list = r.json()
check("/api/bots returns list of 6", isinstance(bots_list, list) and len(bots_list) == 6)

# /api/bots/<name>
r = s.get(f"{BASE}/api/bots/stable_bot", timeout=2)
check("/api/bots/stable_bot → 200", r.status_code == 200)
b = r.json()
check("Bot state has 'status' field", "status" in b)
check("Bot state has 'pid' field", "pid" in b)
check("Bot state has 'uptime_s' field", "uptime_s" in b)
check("Bot state has 'restart_count' field", "restart_count" in b)
check("Bot state has 'cpu_percent' field", "cpu_percent" in b)
check("Bot state has 'memory_mb' field", "memory_mb" in b)
check("Bot state has 'config' field", "config" in b)
check("Bot state has 'history' field (list)", isinstance(b.get("history"), list))

# SECRET MASKING: token must NOT appear in plain text in API response.
text = r.text
check("TOKEN not leaked in API response", "sk-stable-1234567890abcdef" not in text,
      "raw token found in response!")
check("SECRET not leaked in API response", "very-secret-value-xyz" not in text,
      "raw secret found in response!")
check("TOKEN masked (starts with first 4 chars)", "sk-s" in text,
      "mask prefix not found")
check("TOKEN masked (ends with last 4 chars)", "cdef" in text,
      "mask suffix not found")

# /api/bots/<unknown> → 404
r = s.get(f"{BASE}/api/bots/does_not_exist", timeout=2)
check("/api/bots/<unknown> → 404", r.status_code == 404)

# /api/supervisor_log
r = s.get(f"{BASE}/api/supervisor_log?lines=50", timeout=2)
check("/api/supervisor_log → 200", r.status_code == 200)
check("/api/supervisor_log is text/plain",
      "text/plain" in r.headers.get("Content-Type", ""))
if r.text:
    # The supervisor log buffer is capped at 500 lines — verbose_bot can
    # flood it and push older lines out. Just verify SOME bot name appears.
    any_bot = any(name in r.text for name in
                  ["stable_bot", "crashy_bot", "verbose_bot", "argv_bot", "stubborn_bot"])
    check("Supervisor log contains a bot name", any_bot,
          f"got {len(r.text)} chars: {r.text[:200]!r}")
else:
    check("Supervisor log contains a bot name", False, "response was empty")

# /api/bots/<name>/logs
r = s.get(f"{BASE}/api/bots/stable_bot/logs?lines=50", timeout=2)
check("/api/bots/stable_bot/logs → 200", r.status_code == 200)
check("Bot logs contain startup message", "STABLE_BOT" in r.text or "stable_bot" in r.text,
      f"got: {r.text[:200]}")

# /api/bots/<unknown>/logs → 404
r = s.get(f"{BASE}/api/bots/ghost/logs", timeout=2)
check("/api/bots/<unknown>/logs → 404", r.status_code == 404)

# /api/metrics/history/<name>
r = s.get(f"{BASE}/api/metrics/history/stable_bot", timeout=2)
check("/api/metrics/history/stable_bot → 200", r.status_code == 200)
hist = r.json()
check("Metrics history is a list", isinstance(hist, list))
if hist:
    sample = hist[0]
    check("History sample has 't' (timestamp)", "t" in sample)
    check("History sample has 'cpu'", "cpu" in sample)
    check("History sample has 'mem'", "mem" in sample)
else:
    skip("History sample structure (no samples yet)", "history empty")

# Wait a few seconds for metrics to accumulate.
print("    Waiting 6s for metrics samples...")
time.sleep(6)
r = s.get(f"{BASE}/api/metrics/history/stable_bot", timeout=2)
hist = r.json()
check("Metrics history grew after waiting (>=1 sample)", len(hist) >= 1,
      f"got {len(hist)} samples")

# ---------------------------------------------------------------------------
# SECTION 5: Bot actions via API
# ---------------------------------------------------------------------------
section("5. BOT ACTIONS VIA API (start/stop/restart/enable/disable)")

# Get fresh CSRF token.
r = s.get(f"{BASE}/", timeout=2)
m = re.search(r'const csrf = "([^"]+)"', r.text)
CSRF = m.group(1) if m else ""

# Action without CSRF → 403.
r = s.post(f"{BASE}/api/bots/stable_bot/stop", timeout=2)
check("POST without CSRF → 403", r.status_code == 403, f"got {r.status_code}")

# Action with bad CSRF → 403.
r = s.post(f"{BASE}/api/bots/stable_bot/stop",
           headers={"X-CSRF-Token": "garbage"}, timeout=2)
check("POST with bad CSRF → 403", r.status_code == 403)

# Unknown action → 400.
r = s.post(f"{BASE}/api/bots/stable_bot/dance",
           headers={"X-CSRF-Token": CSRF}, timeout=2)
check("Unknown action → 400", r.status_code == 400, f"got {r.status_code}")

# Unknown bot action → 404.
r = s.post(f"{BASE}/api/bots/ghost/stop",
           headers={"X-CSRF-Token": CSRF}, timeout=2)
check("Action on unknown bot → 404", r.status_code == 404)

# STOP stable_bot.
pid_before = s.get(f"{BASE}/api/bots/stable_bot", timeout=2).json().get("pid")
r = s.post(f"{BASE}/api/bots/stable_bot/stop",
           headers={"X-CSRF-Token": CSRF}, timeout=5)
check("POST /stop → 200", r.status_code == 200)
check("Stop response ok=True", r.json().get("ok") is True)
time.sleep(1)
r = s.get(f"{BASE}/api/bots/stable_bot", timeout=2)
check("stable_bot status is 'stopped' after stop",
      r.json().get("status") == "stopped", f"got {r.json().get('status')}")
check("stable_bot pid is None after stop",
      r.json().get("pid") is None, f"got pid={r.json().get('pid')}")
# Verify process actually died.
if pid_before:
    try:
        still_alive = psutil.Process(pid_before).is_running()
        check(f"Old PID {pid_before} is no longer running", not still_alive,
              f"process still alive!")
    except psutil.NoSuchProcess:
        check(f"Old PID {pid_before} is no longer running", True)

# START stable_bot.
r = s.post(f"{BASE}/api/bots/stable_bot/start",
           headers={"X-CSRF-Token": CSRF}, timeout=5)
check("POST /start → 200", r.status_code == 200)
check("Start response ok=True", r.json().get("ok") is True)
time.sleep(1.5)
r = s.get(f"{BASE}/api/bots/stable_bot", timeout=2)
check("stable_bot status is 'running' after start",
      r.json().get("status") == "running", f"got {r.json().get('status')}")
pid_after_start = r.json().get("pid")
check("stable_bot has new PID after start", pid_after_start is not None and pid_after_start != pid_before)

# RESTART stable_bot (should get yet another PID).
r = s.post(f"{BASE}/api/bots/stable_bot/restart",
           headers={"X-CSRF-Token": CSRF}, timeout=5)
check("POST /restart → 200", r.status_code == 200)
time.sleep(1.5)
r = s.get(f"{BASE}/api/bots/stable_bot", timeout=2)
check("stable_bot running after restart",
      r.json().get("status") == "running")
pid_after_restart = r.json().get("pid")
check("stable_bot has new PID after restart",
      pid_after_restart != pid_after_start,
      f"pids equal: {pid_after_start} == {pid_after_restart}")

# ENABLE stubborn_bot (was disabled in config).
r = s.post(f"{BASE}/api/bots/stubborn_bot/enable",
           headers={"X-CSRF-Token": CSRF}, timeout=5)
check("POST /enable stubborn_bot → 200", r.status_code == 200)
time.sleep(2)
r = s.get(f"{BASE}/api/bots/stubborn_bot", timeout=2)
check("stubborn_bot running after enable",
      r.json().get("status") == "running", f"got {r.json().get('status')}")
stubborn_pid = r.json().get("pid")
check("stubborn_bot wrote pid file",
      (BOTS_DIR / "stubborn_bot" / "pid.stubborn").exists())

# DISABLE stable_bot.
r = s.post(f"{BASE}/api/bots/stable_bot/disable",
           headers={"X-CSRF-Token": CSRF}, timeout=5)
check("POST /disable stable_bot → 200", r.status_code == 200)
time.sleep(1.5)
r = s.get(f"{BASE}/api/bots/stable_bot", timeout=2)
check("stable_bot status is 'disabled' after disable",
      r.json().get("status") == "disabled", f"got {r.json().get('status')}")

# Re-enable stable_bot for the rest of the audit.
r = s.post(f"{BASE}/api/bots/stable_bot/enable",
           headers={"X-CSRF-Token": CSRF}, timeout=5)
time.sleep(1.5)

# ---------------------------------------------------------------------------
# SECTION 6: Process supervision — crash auto-restart
# ---------------------------------------------------------------------------
section("6. PROCESS SUPERVISION (auto-restart on crash)")

# crashy_bot should have already crashed and restarted several times.
r = s.get(f"{BASE}/api/bots/crashy_bot", timeout=2)
cb = r.json()
check("crashy_bot has restart_count > 0",
      cb.get("restart_count", 0) > 0, f"got {cb.get('restart_count')}")
check("crashy_bot last_exit_code is 2",
      cb.get("last_exit_code") == 2, f"got {cb.get('last_exit_code')}")

# Wait for it to hit max_restarts (3) and give up.
print("    Waiting 10s for crashy_bot to hit max_restarts...")
deadline = time.time() + 15
gave_up = False
while time.time() < deadline:
    r = s.get(f"{BASE}/api/bots/crashy_bot", timeout=2)
    cb = r.json()
    if cb.get("restart_count", 0) >= 3 and cb.get("status") == "crashed":
        gave_up = True
        break
    time.sleep(0.5)
check("crashy_bot hit max_restarts=3 and gave up (status=crashed)",
      gave_up, f"final state: restarts={cb.get('restart_count')}, status={cb.get('status')}")

# Manually restart crashy_bot to prove the supervisor can recover.
r = s.post(f"{BASE}/api/bots/crashy_bot/restart",
           headers={"X-CSRF-Token": CSRF}, timeout=5)
check("Manual restart of crashy_bot accepted", r.status_code == 200)

# ---------------------------------------------------------------------------
# SECTION 7: SIGKILL fallback for stubborn bots
# ---------------------------------------------------------------------------
section("7. SIGKILL FALLBACK (stubborn bot that ignores SIGTERM)")

# Stop stubborn_bot — it ignores SIGTERM, so supervisor should SIGKILL it.
# This takes ~timeout_graceful seconds (default 10s) before SIGKILL fires.
r = s.post(f"{BASE}/api/bots/stubborn_bot/stop",
           headers={"X-CSRF-Token": CSRF}, timeout=30)
check("Stop stubborn_bot → 200", r.status_code == 200)
# Verify the process is actually gone (despite ignoring SIGTERM).
if stubborn_pid:
    time.sleep(1)
    try:
        still_alive = psutil.Process(stubborn_pid).is_running()
        check(f"Stubborn bot PID {stubborn_pid} killed via SIGKILL fallback",
              not still_alive, "process still alive after stop!")
    except psutil.NoSuchProcess:
        check(f"Stubborn bot PID {stubborn_pid} killed via SIGKILL fallback", True)

# ---------------------------------------------------------------------------
# SECTION 8: Log drainage (verbose bot)
# ---------------------------------------------------------------------------
section("8. LOG DRAINAGE (verbose bot)")

# verbose_bot prints every 0.1s. After a few seconds, we should see many lines.
r = s.get(f"{BASE}/api/bots/verbose_bot/logs?lines=200", timeout=2)
check("Verbose bot logs endpoint → 200", r.status_code == 200)
lines = r.text.strip().split("\n") if r.text.strip() else []
check("Verbose bot produced log lines (>=5)", len(lines) >= 5,
      f"got {len(lines)} lines")
if lines:
    check("Log lines contain 'VERBOSE_BOT'", any("VERBOSE_BOT" in l for l in lines))

# ---------------------------------------------------------------------------
# SECTION 9: Logout flow
# ---------------------------------------------------------------------------
section("9. LOGOUT FLOW")

r = s.post(f"{BASE}/logout", allow_redirects=False, timeout=2)
check("POST /logout → 302", r.status_code == 302, f"got {r.status_code}")

# After logout, dashboard should redirect.
r = s.get(f"{BASE}/", allow_redirects=False, timeout=2)
check("After logout, / redirects to /login",
      r.status_code == 302 and "/login" in r.headers.get("Location", ""),
      f"got {r.status_code}, Location={r.headers.get('Location')}")

# API also gated after logout.
r = s.get(f"{BASE}/api/status", allow_redirects=False, timeout=2)
check("After logout, /api/status gated",
      r.status_code in (301, 302, 401, 403), f"got {r.status_code}")

# ---------------------------------------------------------------------------
# SECTION 10: Graceful shutdown (SIGTERM)
# ---------------------------------------------------------------------------
section("10. GRACEFUL SHUTDOWN (SIGTERM)")

# Use a fresh session — the previous one was logged out in section 9.
# Wait for the rate limiter window to clear (we used 5+ attempts in section 2).
print("    Waiting 60s for rate limiter window to clear...")
time.sleep(62)

s2 = requests.Session()
r = s2.post(f"{BASE}/login", data={"password": PASSWORD}, timeout=2)
# Note: requests follows redirects by default, so a successful login (302 → /)
# ends up as 200 (the dashboard page). A failed login returns 401.
check("Re-login for shutdown test", r.status_code in (200, 302), f"got {r.status_code}")

# Get current bot PIDs.
r = s2.get(f"{BASE}/api/status", timeout=2)
if r.status_code == 200:
    bots_before = {b["name"]: b.get("pid") for b in r.json().get("bots", [])}
else:
    bots_before = {}
running_pids = {k: v for k, v in bots_before.items() if v is not None}
print(f"    Running bot PIDs before SIGTERM: {running_pids}")

# Send SIGTERM to the dashboard.
print(f"    Sending SIGTERM to dashboard process (pid={proc.pid})...")
t0 = time.time()
proc.send_signal(signal.SIGTERM)

# Wait for it to exit.
try:
    proc.wait(timeout=15)
    exit_code = proc.returncode
    elapsed = time.time() - t0
    check("Dashboard exited within 15s of SIGTERM", True)
    check(f"Dashboard exit code is 0 (clean)", exit_code == 0,
          f"got exit_code={exit_code}")
    check(f"Shutdown was fast (<5s)", elapsed < 5.0,
          f"took {elapsed:.2f}s")
except subprocess.TimeoutExpired:
    check("Dashboard exited within 15s of SIGTERM", False,
          "timed out — had to kill")
    proc.kill()
    proc.wait()
    elapsed = time.time() - t0

# Verify all bot subprocesses are gone (no orphans).
time.sleep(1)
orphans = []
for name, pid in running_pids.items():
    if pid is None:
        continue
    try:
        if psutil.Process(pid).is_running():
            orphans.append((name, pid))
    except psutil.NoSuchProcess:
        pass  # good
check(f"No orphan bot processes after shutdown ({len(running_pids)} checked)",
      len(orphans) == 0,
      f"orphans: {orphans}")

# Verify the dashboard is no longer listening.
try:
    requests.get(f"{BASE}/healthz", timeout=1)
    check("Dashboard port closed after shutdown", False, "still responding")
except requests.RequestException:
    check("Dashboard port closed after shutdown", True)

# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------
section("AUDIT SUMMARY")
print(f"  Passed:    {PASS}")
print(f"  Failed:    {FAIL}")
print(f"  Skipped:   {SKIPPED}")
print(f"  Total:     {PASS + FAIL + SKIPPED}")

if FAIL > 0:
    print(f"\n  FAILURES:")
    for name, detail in FAILURES:
        print(f"    ✗ {name}")
        if detail:
            print(f"        {detail}")
    print("\n  ❌ AUDIT FAILED — see failures above.")
    sys.exit(1)
else:
    print(f"\n  ✅ AUDIT PASSED — all {PASS} checks succeeded.")
    sys.exit(0)
