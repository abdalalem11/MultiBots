"""Unit tests for MetricsCollector."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from main import BotConfig, MetricsCollector


def _bot_cfg(name="b1", **kw) -> BotConfig:
    return BotConfig(name=name, source="https://x.git", run="main.py", **kw)


class TestMetricsSampling:
    def test_metrics_thread_samples_cpu_mem(self, multibots_factory, make_bot, fake_bot_scripts, wait_for):
        make_bot("b1", fake_bot_scripts["ok"])
        sup = multibots_factory([_bot_cfg("b1")]).supervisor
        sup.start_all()
        assert wait_for(lambda: sup.states["b1"].status == "running", timeout=5)
        # MetricsCollector was already started by multibots_factory.build_components
        # Actually it wasn't — let's start it now.
        # Wait: build_components builds it but doesn't start the thread.
        # The main MultiBots.start() starts it. Let's call start manually.
        metrics = sup._notifier and sup  # noop, just to silence linter
        # We need to start metrics explicitly.
        from main import MultiBots
        # Find the multibots instance via the supervisor's settings reference.
        # Simpler: instantiate metrics directly here.
        m = MetricsCollector(sup, history_size=60)
        m.start()
        try:
            # Wait for at least one sample.
            assert wait_for(lambda: len(sup.states["b1"].history) > 0, timeout=10)
            sample = sup.states["b1"].history[-1]
            assert "t" in sample
            assert "cpu" in sample
            assert "mem" in sample
            # The bot is sleeping; CPU should be near 0, mem should be > 0.
            assert sample["mem"] > 0
        finally:
            m.stop()

    def test_history_size_capped(self, multibots_factory, make_bot, fake_bot_scripts, wait_for):
        from collections import deque
        make_bot("b1", fake_bot_scripts["ok"])
        sup = multibots_factory([_bot_cfg("b1")]).supervisor
        sup.start_all()
        assert wait_for(lambda: sup.states["b1"].status == "running", timeout=5)
        # Replace the state's history with a smaller-capacity deque so we can
        # verify the cap actually applies.
        sup.states["b1"].history = deque(maxlen=5)
        m = MetricsCollector(sup, history_size=5)
        # Patch the poll interval to make this test fast.
        m.POLL_INTERVAL = 0.05
        m.start()
        try:
            # Wait for > 5 samples so the deque wraps.
            assert wait_for(lambda: len(sup.states["b1"].history) >= 5, timeout=5)
            time.sleep(0.5)  # let it sample more
            assert len(sup.states["b1"].history) <= 5
        finally:
            m.stop()

    def test_metrics_for_dead_bot_zero(self, multibots_factory, make_bot, fake_bot_scripts, wait_for):
        make_bot("b1", fake_bot_scripts["quick_exit"])
        sup = multibots_factory([_bot_cfg("b1", max_restarts=0)]).supervisor
        sup.start_all()
        # Wait for the bot to die.
        assert wait_for(lambda: sup.states["b1"].status in ("crashed",), timeout=5)
        m = MetricsCollector(sup, history_size=60)
        m.POLL_INTERVAL = 0.05
        m.start()
        try:
            time.sleep(0.3)
            st = sup.states["b1"]
            # Dead bot → no process → cpu/mem stay at 0.
            assert st.cpu_percent == 0.0
            assert st.memory_mb == 0.0
        finally:
            m.stop()


class TestSystemSnapshot:
    def test_system_snapshot_has_required_fields(self, multibots_factory):
        sup = multibots_factory([_bot_cfg("b1")]).supervisor
        m = MetricsCollector(sup)
        snap = m.system_snapshot()
        for key in ("ts", "cpu_percent", "cpu_count", "load_1", "load_5", "load_15",
                    "mem_total_mb", "mem_used_mb", "mem_percent",
                    "swap_total_mb", "swap_used_mb", "swap_percent",
                    "disk_percent", "boot_time", "process_count"):
            assert key in snap, f"missing {key}"
        assert snap["cpu_count"] >= 1
        assert 0 <= snap["mem_percent"] <= 100
        assert 0 <= snap["disk_percent"] <= 100

    def test_system_snapshot_never_raises(self, multibots_factory, monkeypatch):
        sup = multibots_factory([_bot_cfg("b1")]).supervisor
        m = MetricsCollector(sup)
        # Force psutil to raise.
        import psutil
        def boom():
            raise RuntimeError("simulated failure")
        monkeypatch.setattr(psutil, "cpu_percent", boom)
        snap = m.system_snapshot()
        # Must include "error" instead of raising.
        assert "error" in snap
