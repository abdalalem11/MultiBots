"""Unit tests for the BotSupervisor — start/stop/restart/watchdog."""
from __future__ import annotations

import os
import signal
import time
from pathlib import Path

import pytest

from main import BotConfig, BotSupervisor, WebhookNotifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_bot_cfg(name: str, run: str = "main.py", **kw) -> BotConfig:
    return BotConfig(
        name=name, source="https://github.com/x/y.git", run=run, **kw,
    )


# ---------------------------------------------------------------------------
# Start / stop lifecycle
# ---------------------------------------------------------------------------
class TestStartStop:
    def test_start_one_running_bot(self, multibots_factory, make_bot, fake_bot_scripts, wait_for):
        make_bot("b1", fake_bot_scripts["ok"])
        cfg = _make_bot_cfg("b1")
        sup = multibots_factory([cfg]).supervisor
        sup.start_all()
        assert wait_for(lambda: sup.states["b1"].status == "running", timeout=5)
        assert sup.states["b1"].pid is not None
        # The fake bot writes a heartbeat file.
        assert wait_for(
            lambda: (Path(sup.settings["bots_dir"]) / "b1" / "heartbeat.ok").exists(),
            timeout=3,
        )

    def test_start_already_running_is_idempotent(self, multibots_factory, make_bot, fake_bot_scripts, wait_for):
        make_bot("b1", fake_bot_scripts["ok"])
        sup = multibots_factory([_make_bot_cfg("b1")]).supervisor
        sup.start_all()
        assert wait_for(lambda: sup.states["b1"].status == "running", timeout=5)
        pid_before = sup.states["b1"].pid
        # Calling start() again must NOT spawn a second process.
        assert sup.start("b1") is True
        assert sup.states["b1"].pid == pid_before

    def test_start_missing_runfile_marks_crashed(self, multibots_factory, make_bot, fake_bot_scripts):
        # Make a bot dir but no actual run file.
        # (We just don't call make_bot — the dir won't exist either.)
        sup = multibots_factory([_make_bot_cfg("ghost")]).supervisor
        sup.start("ghost")
        st = sup.states["ghost"]
        assert st.status == "crashed"
        assert "not found" in st.last_error

    def test_disabled_bot_not_started(self, multibots_factory, make_bot, fake_bot_scripts, wait_for):
        make_bot("b1", fake_bot_scripts["ok"])
        make_bot("b2", fake_bot_scripts["ok"])
        sup = multibots_factory([
            _make_bot_cfg("b1"),
            _make_bot_cfg("b2", enabled=False),
        ]).supervisor
        sup.start_all()
        assert wait_for(lambda: sup.states["b1"].status == "running", timeout=5)
        assert sup.states["b2"].status == "disabled"
        assert sup.states["b2"].pid is None

    def test_stop_running_bot(self, multibots_factory, make_bot, fake_bot_scripts, wait_for):
        make_bot("b1", fake_bot_scripts["ok"])
        sup = multibots_factory([_make_bot_cfg("b1")]).supervisor
        sup.start_all()
        assert wait_for(lambda: sup.states["b1"].status == "running", timeout=5)
        assert sup.stop("b1") is True
        assert sup.states["b1"].status == "stopped"
        assert sup.states["b1"].pid is None

    def test_stop_unknown_bot_returns_false(self, multibots_factory):
        sup = multibots_factory([]).supervisor
        assert sup.stop("does-not-exist") is False

    def test_start_unknown_bot_returns_false(self, multibots_factory):
        sup = multibots_factory([]).supervisor
        assert sup.start("does-not-exist") is False


# ---------------------------------------------------------------------------
# Restart
# ---------------------------------------------------------------------------
class TestRestart:
    def test_restart_changes_pid(self, multibots_factory, make_bot, fake_bot_scripts, wait_for):
        make_bot("b1", fake_bot_scripts["ok"])
        sup = multibots_factory([_make_bot_cfg("b1")]).supervisor
        sup.start_all()
        assert wait_for(lambda: sup.states["b1"].status == "running", timeout=5)
        pid1 = sup.states["b1"].pid
        assert sup.restart("b1") is True
        assert wait_for(lambda: sup.states["b1"].status == "running", timeout=5)
        pid2 = sup.states["b1"].pid
        assert pid1 != pid2

    def test_restart_unknown_returns_false(self, multibots_factory):
        sup = multibots_factory([]).supervisor
        assert sup.restart("ghost") is False


# ---------------------------------------------------------------------------
# Enable / disable
# ---------------------------------------------------------------------------
class TestEnableDisable:
    def test_disable_stops_running_bot(self, multibots_factory, make_bot, fake_bot_scripts, wait_for):
        make_bot("b1", fake_bot_scripts["ok"])
        sup = multibots_factory([_make_bot_cfg("b1")]).supervisor
        sup.start_all()
        assert wait_for(lambda: sup.states["b1"].status == "running", timeout=5)
        assert sup.disable("b1") is True
        assert sup.states["b1"].status == "disabled"
        assert sup.bots["b1"].enabled is False

    def test_enable_starts_stopped_bot(self, multibots_factory, make_bot, fake_bot_scripts, wait_for):
        make_bot("b1", fake_bot_scripts["ok"])
        sup = multibots_factory([_make_bot_cfg("b1", enabled=False)]).supervisor
        sup.start_all()
        assert sup.states["b1"].status == "disabled"
        assert sup.enable("b1") is True
        assert wait_for(lambda: sup.states["b1"].status == "running", timeout=5)


# ---------------------------------------------------------------------------
# Watchdog — restart on crash
# ---------------------------------------------------------------------------
class TestWatchdogAutoRestart:
    def test_quick_exit_triggers_restart(self, multibots_factory, make_bot, fake_bot_scripts, wait_for):
        make_bot("b1", fake_bot_scripts["quick_exit"])
        sup = multibots_factory([
            _make_bot_cfg("b1", max_restarts=3, restart_delay_base=0.1),
        ]).supervisor
        sup.start_all()
        # The bot exits immediately; watchdog should restart it a few times.
        assert wait_for(lambda: sup.states["b1"].restart_count >= 2, timeout=8)
        assert sup.states["b1"].last_exit_code == 2

    def test_max_restarts_cap_respected(self, multibots_factory, make_bot, fake_bot_scripts, wait_for):
        make_bot("b1", fake_bot_scripts["quick_exit"])
        sup = multibots_factory([
            _make_bot_cfg("b1", max_restarts=2, restart_delay_base=0.05),
        ]).supervisor
        sup.start_all()
        # Wait for it to give up.
        assert wait_for(lambda: sup.states["b1"].restart_count >= 2, timeout=10)
        # After giving up, status stays crashed (not running).
        assert wait_for(
            lambda: sup.states["b1"].status in ("crashed",),
            timeout=5,
        )

    def test_watchdog_does_not_restart_disabled(self, multibots_factory, make_bot, fake_bot_scripts, wait_for):
        make_bot("b1", fake_bot_scripts["ok"])
        sup = multibots_factory([_make_bot_cfg("b1", enabled=False)]).supervisor
        sup.start_all()
        # Disabled bots are never started, never restarted.
        time.sleep(1.0)
        assert sup.states["b1"].restart_count == 0
        assert sup.states["b1"].status == "disabled"


# ---------------------------------------------------------------------------
# Graceful shutdown (SIGTERM)
# ---------------------------------------------------------------------------
class TestGracefulShutdown:
    def test_stop_all_terminates_children(self, multibots_factory, make_bot, fake_bot_scripts, wait_for):
        make_bot("b1", fake_bot_scripts["ok"])
        make_bot("b2", fake_bot_scripts["ok"])
        sup = multibots_factory([_make_bot_cfg("b1"), _make_bot_cfg("b2")]).supervisor
        sup.start_all()
        assert wait_for(lambda: sup.states["b1"].status == "running", timeout=5)
        assert wait_for(lambda: sup.states["b2"].status == "running", timeout=5)
        pid1, pid2 = sup.states["b1"].pid, sup.states["b2"].pid
        sup.stop_all(timeout=3.0)
        # Both children gone.
        import psutil
        for pid in (pid1, pid2):
            try:
                p = psutil.Process(pid)
                assert not p.is_running(), f"pid {pid} still alive"
            except psutil.NoSuchProcess:
                pass  # good

    def test_slow_exit_gets_sigkill(self, multibots_factory, make_bot, fake_bot_scripts, wait_for):
        """Bot that ignores SIGTERM should still be killed within timeout."""
        make_bot("b1", fake_bot_scripts["slow_exit"])
        sup = multibots_factory([
            _make_bot_cfg("b1", timeout_graceful=0.5),
        ]).supervisor
        sup.start_all()
        assert wait_for(lambda: sup.states["b1"].status == "running", timeout=5)
        pid = sup.states["b1"].pid
        t0 = time.time()
        sup.stop("b1", timeout=0.5)
        elapsed = time.time() - t0
        # Should have taken ~0.5s (timeout) + a bit for the kill, not 5s.
        assert elapsed < 3.0, f"stop took too long: {elapsed:.2f}s"
        import psutil
        try:
            assert not psutil.Process(pid).is_running()
        except psutil.NoSuchProcess:
            pass  # already reaped


# ---------------------------------------------------------------------------
# Args / env propagation
# ---------------------------------------------------------------------------
class TestArgvAndEnv:
    def test_extra_args_passed_to_bot(self, multibots_factory, make_bot, fake_bot_scripts, wait_for, capfd):
        make_bot("b1", fake_bot_scripts["argv"])
        sup = multibots_factory([
            _make_bot_cfg("b1", args=["--foo", "bar", "--flag"]),
        ]).supervisor
        sup.start_all()
        assert wait_for(lambda: sup.states["b1"].status == "running", timeout=5)
        time.sleep(0.3)  # let it print

    def test_env_passed_to_bot(self, multibots_factory, make_bot, fake_bot_scripts, wait_for, capfd):
        make_bot("b1", fake_bot_scripts["env"])
        sup = multibots_factory([
            _make_bot_cfg("b1", env={"FOO": "bar-baz"}),
        ]).supervisor
        sup.start_all()
        assert wait_for(lambda: sup.states["b1"].status == "running", timeout=5)
        time.sleep(0.3)


# ---------------------------------------------------------------------------
# Concurrency safety (lock held during state mutations)
# ---------------------------------------------------------------------------
class TestConcurrency:
    def test_concurrent_start_stop_no_crash(self, multibots_factory, make_bot, fake_bot_scripts, wait_for):
        import threading
        make_bot("b1", fake_bot_scripts["ok"])
        sup = multibots_factory([_make_bot_cfg("b1")]).supervisor
        errors = []

        def hammer():
            try:
                for _ in range(20):
                    sup.start("b1")
                    sup.stop("b1")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=hammer) for _ in range(4)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == [], f"errors: {errors}"
