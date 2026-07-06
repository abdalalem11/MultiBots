"""
Shared pytest fixtures for the MultiBots test-suite.

Most tests build a tiny "fake bot" Python script that just sleeps — this
lets us exercise the supervisor without depending on real Telegram bots
or network access.
"""
from __future__ import annotations

import json
import os
import sys
import textwrap
import time
from pathlib import Path

import pytest

# Make sure the repo root is on sys.path so `import main` / `import dashboard` works.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Fake bot scripts — what we'll actually launch from the supervisor in tests.
# ---------------------------------------------------------------------------
FAKE_BOT_OK = textwrap.dedent("""
    import os, sys, time
    print("fake-bot-ok: pid=%s parent=%s" % (os.getpid(), os.getppid()), flush=True)
    # Write a heartbeat file so tests can prove the bot actually started.
    with open(os.path.join(os.getcwd(), "heartbeat.ok"), "w") as fh:
        fh.write(str(os.getpid()))
    while True:
        time.sleep(0.5)
""").strip()

FAKE_BOT_QUICK_EXIT = textwrap.dedent("""
    import os, sys
    print("fake-bot-quick: exiting immediately", flush=True)
    sys.exit(2)
""").strip()

FAKE_BOT_SLOW_EXIT = textwrap.dedent("""
    import os, sys, signal, time
    print("fake-bot-slow: will exit on SIGTERM after 5s", flush=True)
    # Write pid file so test can verify graceful shutdown
    with open(os.path.join(os.getcwd(), "pid.slow"), "w") as fh:
        fh.write(str(os.getpid()))

    def _term(signum, frame):
        print("fake-bot-slow: got SIGTERM, sleeping 5s then exiting", flush=True)
        time.sleep(5)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _term)
    while True:
        time.sleep(0.5)
""").strip()

FAKE_BOT_ARGV = textwrap.dedent("""
    import sys
    print("argv=" + repr(sys.argv[1:]), flush=True)
    import time
    while True:
        time.sleep(0.5)
""").strip()

FAKE_BOT_ENV = textwrap.dedent("""
    import os, time
    print("FOO=" + os.environ.get("FOO", "<unset>"), flush=True)
    while True:
        time.sleep(0.5)
""").strip()


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def settings(tmp_path) -> dict:
    """Settings dict pointing at a temp directory (no /app pollution)."""
    from main import DEFAULTS
    bots_dir = tmp_path / "bots"
    bots_dir.mkdir()
    log_dir = tmp_path / "logs"
    return {
        **DEFAULTS,
        "bots_dir": str(bots_dir),
        "log_dir": str(log_dir),
        "config_path": str(tmp_path / "config.json"),
        "start_delay": 0.05,
        "watchdog_interval": 0.3,
        "max_restarts": 3,
        "restart_delay_base": 0.1,
        "restart_delay_max": 1.0,
        "ping_interval": 9999,        # disable pinger in tests
        "ping_url": "http://127.0.0.1:65535/",  # unreachable, no exception
        "webhook_url": "",
        "shutdown_timeout": 5.0,
        "metrics_history": 60,
        "dashboard_password_hash": "",  # auto-gen in dashboard tests
        "dashboard_session_secret": "test-secret-do-not-use-in-prod",
    }


@pytest.fixture
def make_bot(tmp_path, settings):
    """Factory: create a bot dir + entry script, return (name, path)."""
    created = []

    def _make(name: str, script: str, run_file: str = "main.py",
              extra_files: dict | None = None):
        bots_dir = Path(settings["bots_dir"])
        bot_dir = bots_dir / name
        bot_dir.mkdir(parents=True, exist_ok=True)
        (bot_dir / run_file).write_text(script)
        for fn, content in (extra_files or {}).items():
            (bot_dir / fn).write_text(content)
        created.append(name)
        return name, str(bot_dir / run_file)

    yield _make


@pytest.fixture
def write_config(tmp_path, settings):
    """Factory: write a config.json file with the given bots dict."""
    def _write(bots: dict, dashboard: dict | None = None, global_cfg: dict | None = None):
        cfg: dict = {}
        if dashboard:
            cfg["_dashboard"] = dashboard
        if global_cfg:
            cfg["_global"] = global_cfg
        cfg.update(bots)
        path = Path(settings["config_path"])
        path.write_text(json.dumps(cfg, indent=2))
        return path
    return _write


@pytest.fixture
def multibots_factory(settings):
    """Factory: build a MultiBots instance from a given bots list."""
    from main import MultiBots
    created = []

    def _build(bots, **overrides):
        s = {**settings, **overrides}
        mb = MultiBots(settings=s)
        mb.bots = bots
        mb.dashboard_cfg = {}
        mb.build_components()
        created.append(mb)
        return mb

    yield _build

    # Cleanup: stop every supervisor we created.
    for mb in created:
        try:
            mb.stop()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers re-exported for convenience
# ---------------------------------------------------------------------------
@pytest.fixture
def wait_for():
    """Poll a condition up to `timeout` seconds. Returns True if it succeeded."""
    def _wait(cond, timeout=5.0, interval=0.05):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if cond():
                    return True
            except Exception:
                pass
            time.sleep(interval)
        return False
    return _wait


@pytest.fixture
def fake_bot_scripts():
    return {
        "ok": FAKE_BOT_OK,
        "quick_exit": FAKE_BOT_QUICK_EXIT,
        "slow_exit": FAKE_BOT_SLOW_EXIT,
        "argv": FAKE_BOT_ARGV,
        "env": FAKE_BOT_ENV,
    }
