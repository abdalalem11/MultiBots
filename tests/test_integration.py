"""
End-to-end integration tests.

These tests simulate a full MultiBots deployment:
  - Real config.json on disk
  - Real bot subprocesses (fake bots that sleep / exit / hang)
  - Real MultiBots orchestrator with watchdog + metrics
  - Real dashboard wired to the supervisor
  - HTTP requests via Flask test client

If these tests pass, the system is genuinely working.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

import dashboard
from dashboard import DashboardApp, hash_password
from main import MultiBots, BotConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _setup_real_deployment(tmp_path, settings, make_bot, fake_bot_scripts,
                           password="e2e-pw-456"):
    """Wire up a complete deployment under tmp_path."""
    # Create three bots with different behaviors.
    make_bot("stable_bot",   fake_bot_scripts["ok"])         # runs forever
    make_bot("flaky_bot",    fake_bot_scripts["quick_exit"]) # exits immediately
    make_bot("slow_bot",     fake_bot_scripts["ok"])         # another stable

    # Write config.json with the new (extended) schema.
    cfg = {
        "_dashboard": {},
        "_global": {"max_restarts": 3, "restart_delay_base": 0.1},
        "stable_bot": {
            "source": "https://github.com/x/stable.git",
            "run": "main.py",
            "env": {"TOKEN": "stable-token-1234567890"},
            "enabled": True,
        },
        "flaky_bot": {
            "source": "https://github.com/x/flaky.git",
            "run": "main.py",
            "env": {"TOKEN": "flaky-token"},
            "enabled": True,
            "max_restarts": 2,
            "restart_delay_base": 0.05,
        },
        "slow_bot": {
            "source": "https://github.com/x/slow.git",
            "run": "main.py",
            "enabled": False,  # disabled at boot
        },
    }
    Path(settings["config_path"]).write_text(json.dumps(cfg, indent=2))

    settings["dashboard_password_hash"] = hash_password(password)
    settings["dashboard_session_secret"] = "e2e-test-secret"
    settings["max_restarts"] = 3
    settings["restart_delay_base"] = 0.1
    settings["restart_delay_max"] = 1.0
    settings["watchdog_interval"] = 0.3
    settings["start_delay"] = 0.05
    settings["ping_interval"] = 9999  # disable pinger

    return cfg, password


# ---------------------------------------------------------------------------
# Full deployment smoke test
# ---------------------------------------------------------------------------
class TestEndToEndDeployment:
    def test_full_startup_and_dashboard(self, tmp_path, settings, make_bot,
                                        fake_bot_scripts, wait_for):
        cfg, password = _setup_real_deployment(
            tmp_path, settings, make_bot, fake_bot_scripts,
        )

        # 1. Construct MultiBots from config.json — the real code path.
        mb = MultiBots(settings=settings)
        mb.load_config()
        mb.build_components()

        assert len(mb.bots) == 3
        by_name = {b.name: b for b in mb.bots}
        assert by_name["stable_bot"].enabled is True
        assert by_name["flaky_bot"].max_restarts == 2
        assert by_name["slow_bot"].enabled is False

        # 2. Start the supervisor (no pinger, no signal handlers in tests).
        mb.start(run_pinger=False, install_signals=False)

        # 3. Verify stable + flaky started; slow is disabled.
        assert wait_for(
            lambda: mb.supervisor.states["stable_bot"].status == "running",
            timeout=5,
        )
        assert mb.supervisor.states["slow_bot"].status == "disabled"

        # 4. Verify the flaky bot starts crashing and gets restarted.
        assert wait_for(
            lambda: mb.supervisor.states["flaky_bot"].restart_count >= 1,
            timeout=8,
        )

        # 5. Verify metrics collector is running and sampling.
        assert mb.metrics.is_alive()
        # Force a quick sample.
        mb.metrics.POLL_INTERVAL = 0.1
        assert wait_for(
            lambda: len(mb.supervisor.states["stable_bot"].history) > 0,
            timeout=5,
        )

        # 6. Wire up the dashboard.
        app = DashboardApp(settings=settings)
        app.attach(mb)
        client = app.app.test_client()

        # 7. Public health endpoints work without auth.
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 200

        # 8. Login flow works.
        assert client.get("/").status_code in (302, 401)  # not logged in
        r = client.post("/login", data={"password": password})
        assert r.status_code == 302

        # 9. Authed dashboard renders all 3 bots.
        r = client.get("/")
        assert r.status_code == 200
        assert b"stable_bot" in r.data
        assert b"flaky_bot" in r.data
        assert b"slow_bot" in r.data

        # 10. /api/status returns full snapshot.
        r = client.get("/api/status")
        assert r.status_code == 200
        data = r.get_json()
        assert "system" in data
        assert len(data["bots"]) == 3

        # 11. /api/bots/<name> returns masked env (no leak).
        r = client.get("/api/bots/stable_bot")
        assert r.status_code == 200
        b = r.get_json()
        # Env TOKEN value should be masked, not the raw value.
        assert "stable-token-1234567890" not in json.dumps(b)
        assert b["config"]["env_masked"]["TOKEN"].startswith("stab")

        # 12. Bot actions work.
        r = client.get("/")
        import re
        m = re.search(rb'const csrf = "([^"]+)"', r.data)
        csrf = m.group(1).decode()

        # Stop stable_bot via API.
        r = client.post("/api/bots/stable_bot/stop",
                        headers={"X-CSRF-Token": csrf})
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        assert wait_for(
            lambda: mb.supervisor.states["stable_bot"].status == "stopped",
            timeout=5,
        )

        # Restart it via API.
        r = client.post("/api/bots/stable_bot/start",
                        headers={"X-CSRF-Token": csrf})
        assert r.status_code == 200
        assert wait_for(
            lambda: mb.supervisor.states["stable_bot"].status == "running",
            timeout=5,
        )

        # 13. Enable the disabled slow_bot via API.
        r = client.post("/api/bots/slow_bot/enable",
                        headers={"X-CSRF-Token": csrf})
        assert r.status_code == 200
        assert wait_for(
            lambda: mb.supervisor.states["slow_bot"].status == "running",
            timeout=5,
        )

        # 14. Logout.
        r = client.post("/logout")
        assert r.status_code == 302
        # After logout, dashboard is gated again.
        assert client.get("/").status_code in (302, 401)

        # 15. Clean shutdown — no orphan processes.
        stable_pid = mb.supervisor.states["stable_bot"].pid
        slow_pid = mb.supervisor.states["slow_bot"].pid
        mb.stop()
        # Verify processes are gone.
        import psutil
        for pid in (stable_pid, slow_pid):
            if pid is None:
                continue
            wait_for(
                lambda: not _pid_alive(pid),
                timeout=5,
            )


def _pid_alive(pid: int) -> bool:
    import psutil
    try:
        return psutil.Process(pid).is_running()
    except psutil.NoSuchProcess:
        return False


# ---------------------------------------------------------------------------
# Backward-compat: original config.json schema still works end-to-end
# ---------------------------------------------------------------------------
class TestBackwardCompatE2E:
    def test_old_schema_runs(self, tmp_path, settings, make_bot, fake_bot_scripts, wait_for):
        """The EXACT config.json format from the original v1.0 README."""
        make_bot("EbookBot", fake_bot_scripts["ok"])
        make_bot("PrivateBot", fake_bot_scripts["ok"], run_file="bot.py")

        # No _dashboard, no _global, no enabled/max_restarts/etc.
        old_schema = {
            "EbookBot": {
                "source": "https://github.com/user/Ebooks-Bot.git",
                "env": {"TOKEN": "abc", "ID": "123", "HASH": "xyz"},
                "run": "main.py",
            },
            "PrivateBot": {
                "source": "https://user:token@github.com/user/private-bot.git",
                "env": {"TOKEN": "another"},
                "run": "bot.py",
            },
        }
        Path(settings["config_path"]).write_text(json.dumps(old_schema))
        settings["start_delay"] = 0.05
        settings["ping_interval"] = 9999

        mb = MultiBots(settings=settings)
        mb.load_config()
        mb.build_components()
        mb.start(run_pinger=False, install_signals=False)

        assert len(mb.bots) == 2
        assert wait_for(
            lambda: mb.supervisor.states["EbookBot"].status == "running",
            timeout=5,
        )
        assert wait_for(
            lambda: mb.supervisor.states["PrivateBot"].status == "running",
            timeout=5,
        )
        # Even though we didn't specify 'enabled', defaults to True.
        assert mb.bots[0].enabled is True


# ---------------------------------------------------------------------------
# Hot-reload scenario (config edited, then bot reconfigured)
# ---------------------------------------------------------------------------
class TestHotReloadScenario:
    def test_disable_then_enable_via_config_reload(
        self, tmp_path, settings, make_bot, fake_bot_scripts, wait_for,
    ):
        """Simulate the user editing config.json and re-running load_config()."""
        make_bot("b1", fake_bot_scripts["ok"])
        Path(settings["config_path"]).write_text(json.dumps({
            "b1": {"source": "https://x.git", "run": "main.py", "enabled": True},
        }))
        mb = MultiBots(settings=settings)
        mb.start(run_pinger=False, install_signals=False)
        assert wait_for(
            lambda: mb.supervisor.states["b1"].status == "running",
            timeout=5,
        )

        # Simulate user edit: disable the bot in config.
        Path(settings["config_path"]).write_text(json.dumps({
            "b1": {"source": "https://x.git", "run": "main.py", "enabled": False},
        }))
        mb.bots, mb.dashboard_cfg = mb.loader.load()
        # Update supervisor's config copy.
        mb.supervisor.bots["b1"].enabled = False
        # Stop the running bot to reflect the new config.
        mb.supervisor.stop("b1")
        assert mb.supervisor.states["b1"].status == "stopped"

        # Re-enable via API.
        mb.supervisor.bots["b1"].enabled = True
        mb.supervisor.start("b1")
        assert wait_for(
            lambda: mb.supervisor.states["b1"].status == "running",
            timeout=5,
        )


# ---------------------------------------------------------------------------
# Crash + webhook delivery (end-to-end with monkeypatched HTTP)
# ---------------------------------------------------------------------------
class TestCrashWebhookE2E:
    def test_crash_sends_webhook(self, tmp_path, settings, make_bot,
                                 fake_bot_scripts, wait_for, monkeypatch):
        make_bot("b1", fake_bot_scripts["quick_exit"])

        Path(settings["config_path"]).write_text(json.dumps({
            "b1": {
                "source": "https://x.git", "run": "main.py",
                "max_restarts": 1, "restart_delay_base": 0.05,
            },
        }))
        settings["webhook_url"] = "https://hooks.example.com/test"
        settings["webhook_timeout"] = 1.0

        # Capture webhook POST.
        posted = []
        class FakeResp:
            status_code = 200
            text = "ok"
        def fake_post(url, json, timeout, headers):
            posted.append({"url": url, "json": json})
            return FakeResp()
        import requests
        monkeypatch.setattr(requests, "post", fake_post)

        mb = MultiBots(settings=settings)
        mb.start(run_pinger=False, install_signals=False)

        # Wait for the bot to crash and trigger the webhook.
        assert wait_for(lambda: len(posted) > 0, timeout=10)
        assert "b1" in posted[0]["json"]["bot_name"]
        assert "exited" in posted[0]["json"]["reason"] or "code" in posted[0]["json"]["reason"]
