"""
MultiBots — Enterprise-grade multi-bot hosting platform
=======================================================

A single-file, modular supervisor that runs multiple Python bots in one
process tree with full process supervision, metrics collection, graceful
shutdown, webhook alerts, and an optional web dashboard.

Design goals
------------
* **Single file, modular sections** — easy to read, easy to copy.
* **Backward compatible** — old ``config.json`` schemas still work.
* **Defensive** — never crashes on a single bad bot, logs everything.
* **Observable** — per-bot metrics, restart counters, structured logs.
* **Scriptable** — every runtime action is also exposed via dashboard.py
  REST endpoints so you can drive MultiBots from CI / cron / chatops.

Sections
--------
1.  Imports & constants
2.  Logging helpers
3.  Configuration layer  (load / validate / env-override / hot-reload)
4.  Metrics collector    (per-bot CPU / RAM / uptime / restarts)
5.  Process supervisor   (start / stop / restart / watchdog)
6.  Webhook notifier     (Slack / Discord / generic HTTP on crash)
7.  Keep-alive pinger    (fixed: 127.0.0.1, no startup race)
8.  Graceful shutdown    (SIGTERM / SIGINT handlers)
9.  Main entry point

The web dashboard lives in ``dashboard.py`` and imports from this file.
"""

# ---------------------------------------------------------------------------
# 1. Imports & constants
# ---------------------------------------------------------------------------
from __future__ import annotations

import errno
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil
import requests

__version__ = "2.0.0"
__all__ = [
    "BotConfig",
    "BotState",
    "BotSupervisor",
    "MetricsCollector",
    "ConfigLoader",
    "WebhookNotifier",
    "MultiBots",
    "DEFAULTS",
    "setup_logging",
    "utc_now_iso",
]

# Defaults — every value here can be overridden via env var or config.json.
DEFAULTS: Dict[str, Any] = {
    "port": int(os.environ.get("MB_PORT", "10000")),
    "host": os.environ.get("MB_HOST", "0.0.0.0"),
    "bots_dir": os.environ.get("MB_BOTS_DIR", "/app"),
    "config_path": os.environ.get("MB_CONFIG_PATH", "config.json"),
    "log_level": os.environ.get("MB_LOG_LEVEL", "INFO"),
    "log_dir": os.environ.get("MB_LOG_DIR", "logs"),
    "log_max_bytes": int(os.environ.get("MB_LOG_MAX_BYTES", str(5 * 1024 * 1024))),
    "log_backup_count": int(os.environ.get("MB_LOG_BACKUP_COUNT", "5")),
    "start_delay": float(os.environ.get("MB_START_DELAY", "2.0")),
    "max_restarts": int(os.environ.get("MB_MAX_RESTARTS", "5")),
    "restart_delay_base": float(os.environ.get("MB_RESTART_DELAY_BASE", "2.0")),
    "restart_delay_max": float(os.environ.get("MB_RESTART_DELAY_MAX", "120.0")),
    "watchdog_interval": float(os.environ.get("MB_WATCHDOG_INTERVAL", "10.0")),
    "ping_interval": float(os.environ.get("MB_PING_INTERVAL", "120.0")),
    "ping_url": os.environ.get("MB_PING_URL", "http://127.0.0.1:10000/"),
    "webhook_url": os.environ.get("MB_WEBHOOK_URL", ""),
    "webhook_timeout": float(os.environ.get("MB_WEBHOOK_TIMEOUT", "5.0")),
    "shutdown_timeout": float(os.environ.get("MB_SHUTDOWN_TIMEOUT", "15.0")),
    "metrics_history": int(os.environ.get("MB_METRICS_HISTORY", "180")),
    "dashboard_enabled": os.environ.get("MB_DASHBOARD_ENABLED", "true").lower()
    in ("1", "true", "yes", "on"),
    # If left empty, dashboard.py will auto-generate one on first run
    # and print it once to stdout. Never hardcode in source.
    "dashboard_password_hash": os.environ.get("MB_DASHBOARD_PASSWORD_HASH", ""),
    "dashboard_session_secret": os.environ.get("MB_DASHBOARD_SESSION_SECRET", ""),
}

# Reserved top-level keys in config.json (not bot definitions).
_RESERVED_KEYS = {"_dashboard", "_global"}

# A bot name must be a valid filesystem-safe identifier.
_BOT_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")

# Required keys for every bot definition.
_REQUIRED_BOT_KEYS = {"source", "run"}

# Optional keys with their default values.
_OPTIONAL_BOT_KEYS: Dict[str, Any] = {
    "env": {},
    "enabled": True,
    "max_restarts": None,        # None = inherit from global
    "restart_delay_base": None,  # None = inherit from global
    "health_url": "",            # optional HTTP health probe
    "health_timeout": 5.0,
    "cwd": None,                 # None = <bots_dir>/<bot_name>
    "python": sys.executable,    # python interpreter to use
    "args": [],                  # extra argv
    "timeout_graceful": 10.0,    # seconds before SIGKILL after SIGTERM
}


# ---------------------------------------------------------------------------
# 2. Logging helpers
# ---------------------------------------------------------------------------
def utc_now_iso() -> str:
    """Return current UTC time as an ISO-8601 string (no microseconds)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def setup_logging(level: str = "INFO", log_dir: Optional[str] = None,
                  max_bytes: int = 5 * 1024 * 1024, backup_count: int = 5) -> logging.Logger:
    """Configure root logger with console + optional rotating file handler.

    Never raises — if file logging fails (read-only fs, no permissions),
    we fall back to console-only logging so the supervisor still runs.
    """
    root = logging.getLogger()
    # Clear any prior handlers (re-config safe).
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler(stream=sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    if log_dir:
        try:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            from logging.handlers import RotatingFileHandler
            file_h = RotatingFileHandler(
                Path(log_dir) / "multibots.log",
                maxBytes=max_bytes, backupCount=backup_count,
                encoding="utf-8",
            )
            file_h.setFormatter(fmt)
            root.addHandler(file_h)
        except OSError as exc:
            # Read-only filesystem or permission denied — don't crash.
            console.setLevel(logging.WARNING)
            logging.getLogger(__name__).warning(
                "File logging disabled (%s); continuing with console only.",
                exc,
            )

    try:
        root.setLevel(level.upper())
    except (ValueError, AttributeError):
        root.setLevel(logging.INFO)

    return logging.getLogger("multibots")


# ---------------------------------------------------------------------------
# 3. Configuration layer
# ---------------------------------------------------------------------------
@dataclass
class BotConfig:
    """Validated configuration for a single bot.

    Created from a single ``config.json`` entry — never holds untrusted
    raw user input after construction.
    """
    name: str
    source: str
    run: str                       # filename inside the bot dir, e.g. "main.py"
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    max_restarts: Optional[int] = None
    restart_delay_base: Optional[float] = None
    health_url: str = ""
    health_timeout: float = 5.0
    cwd: Optional[str] = None
    python: str = field(default_factory=lambda: sys.executable)
    args: List[str] = field(default_factory=list)
    timeout_graceful: float = 10.0

    def resolve_cwd(self, bots_dir: str) -> str:
        """Return absolute working directory for this bot."""
        if self.cwd and os.path.isabs(self.cwd):
            return self.cwd
        return os.path.join(bots_dir, self.name)

    def resolve_runfile(self, bots_dir: str) -> str:
        """Return absolute path to the bot's entry script."""
        return os.path.join(self.resolve_cwd(bots_dir), self.run)

    def to_public_dict(self) -> Dict[str, Any]:
        """Serialize for dashboard/API (env values are masked)."""
        return {
            "name": self.name,
            "source": self.source,
            "run": self.run,
            "enabled": self.enabled,
            "max_restarts": self.max_restarts,
            "restart_delay_base": self.restart_delay_base,
            "health_url": self.health_url,
            "has_env": bool(self.env),
            "env_keys": sorted(self.env.keys()),
            "env_masked": {k: _mask(v) for k, v in self.env.items()},
            "cwd": self.cwd,
            "args": list(self.args),
            "python": self.python,
        }


def _mask(value: str, visible: int = 4) -> str:
    """Mask a secret for safe display: 'sk-1234abcd' → 'sk-1…bcde'."""
    if not value:
        return ""
    if len(value) <= visible * 2:
        return "*" * len(value)
    return f"{value[:visible]}…{value[-visible:]}"


class ConfigError(Exception):
    """Raised when config.json is structurally invalid."""


class ConfigLoader:
    """Load and validate ``config.json`` against the schema.

    The loader is intentionally strict on *structure* (so misconfigured
    bots fail fast at startup instead of producing weird runtime errors)
    but permissive on *content* (unknown optional keys are ignored, not
    rejected — forward compatibility).
    """

    def __init__(self, settings: Dict[str, Any]):
        self.settings = settings

    # ---- public API ------------------------------------------------------
    def load(self, path: Optional[str] = None) -> Tuple[List[BotConfig], Dict[str, Any]]:
        """Load bots + dashboard config from JSON file.

        Returns ``(bots, dashboard_config)``. Bots that fail validation
        are skipped with a warning — one bad bot must never block the
        rest from starting.
        """
        cfg_path = path or self.settings["config_path"]
        raw = self._read_json(cfg_path)
        if not isinstance(raw, dict):
            raise ConfigError(f"{cfg_path}: top-level JSON must be an object")

        dashboard_cfg = raw.get("_dashboard", {}) or {}
        global_cfg = raw.get("_global", {}) or {}

        bots: List[BotConfig] = []
        for name, entry in raw.items():
            if name in _RESERVED_KEYS:
                continue
            try:
                bots.append(self._validate_bot(name, entry, global_cfg))
            except ConfigError as exc:
                logging.getLogger(__name__).error(
                    "Skipping bot '%s': %s", name, exc,
                )
        if not bots:
            logging.getLogger(__name__).warning(
                "Config '%s' contains zero valid bots.", cfg_path,
            )
        return bots, dashboard_cfg

    # ---- internals -------------------------------------------------------
    @staticmethod
    def _read_json(path: str) -> Any:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return __import__("json").load(fh)
        except FileNotFoundError:
            raise ConfigError(f"Config file not found: {path}")
        except __import__("json").JSONDecodeError as exc:
            raise ConfigError(f"Config file {path} is not valid JSON: {exc}")
        except OSError as exc:
            raise ConfigError(f"Cannot read config file {path}: {exc}")

    def _validate_bot(self, name: str, entry: Any,
                      global_cfg: Dict[str, Any]) -> BotConfig:
        if not isinstance(entry, dict):
            raise ConfigError(f"entry must be an object, got {type(entry).__name__}")
        if not _BOT_NAME_RE.match(name):
            raise ConfigError(
                f"bot name must match {_BOT_NAME_RE.pattern!r}",
            )

        missing = _REQUIRED_BOT_KEYS - set(entry)
        if missing:
            raise ConfigError(f"missing required keys: {sorted(missing)}")

        source = str(entry["source"]).strip()
        if not source:
            raise ConfigError("'source' must be a non-empty URL")
        if not source.startswith(("http://", "https://", "git@", "ssh://")):
            raise ConfigError(f"'source' must be a git URL, got {source!r}")

        run = str(entry["run"]).strip()
        if not run:
            raise ConfigError("'run' must be a non-empty filename")
        if os.path.isabs(run) or "/" in run or "\\" in run:
            raise ConfigError(
                f"'run' must be a bare filename (no path separators), got {run!r}",
            )

        env = entry.get("env", {}) or {}
        if not isinstance(env, dict):
            raise ConfigError("'env' must be an object of {string: string}")
        env_str: Dict[str, str] = {}
        for k, v in env.items():
            if not isinstance(k, str) or not k:
                raise ConfigError(f"env key {k!r} must be a non-empty string")
            env_str[k] = str(v)

        # Coerce & validate optional fields with global inheritance.
        def _inherit(key: str, cast):
            val = entry.get(key, _OPTIONAL_BOT_KEYS.get(key))
            if val is None:
                val = global_cfg.get(key, _OPTIONAL_BOT_KEYS.get(key))
            return cast(val) if val is not None else None

        return BotConfig(
            name=name,
            source=source,
            run=run,
            env=env_str,
            enabled=bool(entry.get("enabled", _OPTIONAL_BOT_KEYS["enabled"])),
            max_restarts=_inherit("max_restarts", int),
            restart_delay_base=_inherit("restart_delay_base", float),
            health_url=str(entry.get("health_url", "") or ""),
            health_timeout=float(entry.get("health_timeout", 5.0)),
            cwd=entry.get("cwd"),
            python=str(entry.get("python", _OPTIONAL_BOT_KEYS["python"])),
            args=list(entry.get("args", []) or []),
            timeout_graceful=float(entry.get("timeout_graceful", 10.0)),
        )


# ---------------------------------------------------------------------------
# 4. Metrics collector
# ---------------------------------------------------------------------------
@dataclass
class BotState:
    """Live runtime state of a single bot."""
    config: BotConfig
    process: Optional[subprocess.Popen] = None
    pid: Optional[int] = None
    status: str = "stopped"          # stopped | starting | running | crashed | restarting | disabled
    started_at: Optional[float] = None
    last_exit_code: Optional[int] = None
    restart_count: int = 0
    last_error: str = ""
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    history: deque = field(default_factory=lambda: deque(maxlen=180))

    def resize_history(self, maxlen: int) -> None:
        """Replace the history deque with one of a different capacity,
        preserving existing samples that fit."""
        if maxlen == self.history.maxlen:
            return
        new = deque(self.history, maxlen=maxlen)
        self.history = new

    def uptime_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        return max(0.0, time.time() - self.started_at)

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "name": self.config.name,
            "status": self.status,
            "pid": self.pid,
            "uptime_s": round(self.uptime_seconds(), 1),
            "restart_count": self.restart_count,
            "last_exit_code": self.last_exit_code,
            "last_error": self.last_error,
            "cpu_percent": round(self.cpu_percent, 2),
            "memory_mb": round(self.memory_mb, 2),
            "history": list(self.history),
            "config": self.config.to_public_dict(),
        }


class MetricsCollector(threading.Thread):
    """Background thread that polls per-bot CPU/RAM and stores history.

    Runs as a daemon so it dies with the main process. Polling interval
    is fixed at 5s — short enough for live monitoring, long enough not
    to add measurable overhead even with 50+ bots.
    """
    POLL_INTERVAL = 5.0

    def __init__(self, supervisor: "BotSupervisor", history_size: int = 180):
        super().__init__(name="metrics", daemon=True)
        self.supervisor = supervisor
        self.history_size = history_size
        self._stop = threading.Event()

    def run(self) -> None:
        log = logging.getLogger("multibots.metrics")
        # Initial psutil.cpu_percent call returns 0.0; prime it.
        try:
            psutil.cpu_percent(interval=None)
        except Exception:  # noqa: BLE001 — defensive
            pass
        # Apply the configured history size to every bot state up-front.
        for state in self.supervisor.states.values():
            state.resize_history(self.history_size)
        while not self._stop.is_set():
            try:
                self._sample_once()
            except Exception as exc:  # noqa: BLE001 — must not crash the thread
                log.warning("metrics sample failed: %s", exc)
            self._stop.wait(self.POLL_INTERVAL)

    def stop(self) -> None:
        self._stop.set()

    def _sample_once(self) -> None:
        now = time.time()
        for state in list(self.supervisor.states.values()):
            sample = {"t": now, "cpu": 0.0, "mem": 0.0}
            if state.process and state.process.poll() is None and state.pid:
                try:
                    p = psutil.Process(state.pid)
                    # cpu_percent for a single process is fast & non-blocking.
                    sample["cpu"] = p.cpu_percent(interval=None)
                    sample["mem"] = p.memory_info().rss / (1024 * 1024)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                except Exception:  # noqa: BLE001
                    pass
            state.cpu_percent = sample["cpu"]
            state.memory_mb = sample["mem"]
            state.history.append(sample)

    def system_snapshot(self) -> Dict[str, Any]:
        """One-shot system-wide metrics for the dashboard."""
        try:
            vm = psutil.virtual_memory()
            sm = psutil.swap_memory()
            load1, load5, load15 = psutil.getloadavg()
            return {
                "ts": utc_now_iso(),
                "cpu_percent": psutil.cpu_percent(interval=None),
                "cpu_count": psutil.cpu_count() or 1,
                "load_1": load1, "load_5": load5, "load_15": load15,
                "mem_total_mb": round(vm.total / (1024 * 1024), 1),
                "mem_used_mb": round(vm.used / (1024 * 1024), 1),
                "mem_percent": vm.percent,
                "swap_total_mb": round(sm.total / (1024 * 1024), 1),
                "swap_used_mb": round(sm.used / (1024 * 1024), 1),
                "swap_percent": sm.percent,
                "disk_percent": psutil.disk_usage("/").percent,
                "boot_time": psutil.boot_time(),
                "process_count": len(psutil.pids()),
            }
        except Exception as exc:  # noqa: BLE001 — dashboard must stay up
            return {"ts": utc_now_iso(), "error": str(exc)}


# ---------------------------------------------------------------------------
# 5. Process supervisor
# ---------------------------------------------------------------------------
class BotSupervisor:
    """Starts, watches, and restarts bot subprocesses.

    Threading model: the watchdog runs in its own daemon thread; all
    public methods are safe to call from any thread (state mutations
    are guarded by a single ``threading.RLock``).
    """

    def __init__(self, bots: List[BotConfig], settings: Dict[str, Any]):
        self.bots: Dict[str, BotConfig] = {b.name: b for b in bots}
        self.settings = settings
        self.states: Dict[str, BotState] = {
            name: BotState(config=cfg) for name, cfg in self.bots.items()
        }
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._watchdog: Optional[threading.Thread] = None
        self.log = logging.getLogger("multibots.supervisor")
        self._notifier: Optional[WebhookNotifier] = None

    # ---- lifecycle -------------------------------------------------------
    def attach_notifier(self, notifier: "WebhookNotifier") -> None:
        self._notifier = notifier

    def start_all(self) -> None:
        """Start every enabled bot in config order with a startup delay."""
        with self._lock:
            for name, cfg in self.bots.items():
                if self._stop.is_set():
                    break
                if not cfg.enabled:
                    self.states[name].status = "disabled"
                    self.log.info("Bot '%s' is disabled, skipping.", name)
                    continue
                self._start_one(name)
                # Stagger startup so we don't fork-bomb on cold boot.
                time.sleep(self.settings["start_delay"])
        self._start_watchdog()

    def stop_all(self, timeout: Optional[float] = None) -> None:
        """Stop every running bot, gracefully if possible."""
        self._stop.set()
        self._stop_watchdog()
        timeout = timeout if timeout is not None else self.settings["shutdown_timeout"]
        with self._lock:
            for name in list(self.states.keys()):
                self._stop_one(name, timeout=timeout)

    # ---- per-bot operations ---------------------------------------------
    def start(self, name: str) -> bool:
        """Start a single bot by name. Returns False if unknown/disabled."""
        with self._lock:
            if name not in self.bots:
                return False
            return self._start_one(name)

    def stop(self, name: str, timeout: Optional[float] = None) -> bool:
        with self._lock:
            if name not in self.bots:
                return False
            # Fall back to the bot's configured graceful timeout.
            if timeout is None:
                timeout = self.bots[name].timeout_graceful
            return self._stop_one(name, timeout=timeout)

    def restart(self, name: str) -> bool:
        with self._lock:
            if name not in self.bots:
                return False
            self._stop_one(name, timeout=self.bots[name].timeout_graceful)
            return self._start_one(name)

    def disable(self, name: str) -> bool:
        with self._lock:
            if name not in self.bots:
                return False
            self.bots[name].enabled = False
            self._stop_one(name, timeout=self.bots[name].timeout_graceful)
            self.states[name].status = "disabled"
            return True

    def enable(self, name: str) -> bool:
        with self._lock:
            if name not in self.bots:
                return False
            self.bots[name].enabled = True
            return self._start_one(name)

    # ---- internals: start / stop ----------------------------------------
    def _start_one(self, name: str) -> bool:
        state = self.states[name]
        cfg = self.bots[name]
        if state.process and state.process.poll() is None:
            self.log.warning("Bot '%s' already running (pid=%s).", name, state.pid)
            return True

        bot_cwd = cfg.resolve_cwd(self.settings["bots_dir"])
        run_file = cfg.resolve_runfile(self.settings["bots_dir"])

        if not os.path.isfile(run_file):
            state.status = "crashed"
            state.last_error = f"run file not found: {run_file}"
            self.log.error("Bot '%s' run file missing: %s", name, run_file)
            self._notify_crash(name, state.last_error)
            return False

        env = os.environ.copy()
        env.update({str(k): str(v) for k, v in cfg.env.items()})

        argv = [cfg.python, cfg.run] + list(cfg.args or [])
        try:
            state.status = "starting"
            self.log.info("Starting bot '%s': %s (cwd=%s)", name, argv, bot_cwd)
            state.process = subprocess.Popen(
                argv, cwd=bot_cwd, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                bufsize=1, universal_newlines=True,
            )
            state.pid = state.process.pid
            state.started_at = time.time()
            state.status = "running"
            state.last_error = ""
            # Start a log-drainer thread so logs aren't buffered forever.
            threading.Thread(
                target=self._drain_logs, args=(name,), daemon=True,
                name=f"log-{name}",
            ).start()
            return True
        except OSError as exc:
            state.status = "crashed"
            state.last_error = f"{exc.__class__.__name__}: {exc}"
            state.last_exit_code = exc.errno or -1
            self.log.error("Failed to start bot '%s': %s", name, exc)
            self._notify_crash(name, state.last_error)
            return False

    def _stop_one(self, name: str, timeout: float) -> bool:
        # Note: caller must hold self._lock when calling this.
        state = self.states[name]
        proc = state.process
        if not proc or proc.poll() is not None:
            state.status = "stopped"
            state.process = None
            state.pid = None
            return True
        pid = state.pid
        self.log.info("Stopping bot '%s' (pid=%s)...", name, pid)
        # Mark as "stopped" immediately so the watchdog doesn't try to
        # restart it while we're waiting for SIGTERM to take effect.
        state.status = "stopped"
        try:
            proc.terminate()  # SIGTERM
        except ProcessLookupError:
            pass
        # Release the lock during the (potentially long) wait so other
        # operations (including the watchdog) can proceed.
        self._lock.release()
        try:
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.log.warning("Bot '%s' didn't exit in %.1fs, sending SIGKILL.",
                                 name, timeout)
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    self.log.error("Bot '%s' didn't die after SIGKILL.", name)
        finally:
            self._lock.acquire()
        state.last_exit_code = proc.returncode
        state.process = None
        state.pid = None
        return True

    def _drain_logs(self, name: str) -> None:
        """Read bot stdout line-by-line and forward to Python logging.

        Each bot's lines are tagged ``[bot:<name>]`` so docker logs /
        platform log streams show which bot produced them.
        """
        state = self.states[name]
        proc = state.process
        if not proc or not proc.stdout:
            return
        bot_log = logging.getLogger(f"multibots.bot.{name}")
        try:
            for line in iter(proc.stdout.readline, ""):
                line = line.rstrip()
                if not line:
                    continue
                bot_log.info("%s", line)
        except (ValueError, OSError):
            # stdout closed — bot likely exited; the watchdog will pick it up.
            pass
        finally:
            try:
                proc.stdout.close()
            except Exception:  # noqa: BLE001
                pass

    # ---- internals: watchdog --------------------------------------------
    def _start_watchdog(self) -> None:
        if self._watchdog and self._watchdog.is_alive():
            return
        self._watchdog = threading.Thread(
            target=self._watchdog_loop, daemon=True, name="watchdog",
        )
        self._watchdog.start()

    def _stop_watchdog(self) -> None:
        if self._watchdog and self._watchdog.is_alive():
            self._watchdog.join(timeout=self.settings["watchdog_interval"] * 2)

    def _watchdog_loop(self) -> None:
        interval = self.settings["watchdog_interval"]
        while not self._stop.is_set():
            # Collect the list of bots that need attention WITHOUT holding
            # the lock during the (potentially long) restart-sleep below.
            needs_action: List[Tuple[str, Optional[int]]] = []
            with self._lock:
                for name, state in list(self.states.items()):
                    cfg = self.bots[name]
                    if not cfg.enabled or state.status in ("stopped", "disabled"):
                        continue
                    # Already restarting — skip (the restart path will handle it).
                    if state.status == "restarting":
                        continue
                    # Already gave up — don't keep retrying every iteration.
                    if state.status == "crashed" and state.restart_count >= (
                        cfg.max_restarts if cfg.max_restarts is not None
                        else self.settings["max_restarts"]
                    ):
                        continue
                    if state.process and state.process.poll() is None:
                        continue  # still alive
                    # process died
                    rc = state.process.returncode if state.process else None
                    state.last_exit_code = rc
                    state.status = "crashed"
                    state.last_error = f"exited code={rc}"
                    self.log.warning("Bot '%s' crashed (exit=%s).", name, rc)
                    self._notify_crash(name, state.last_error)
                    needs_action.append((name, rc))
            # Now handle restarts without holding the lock — stop() can
            # proceed concurrently.
            for name, _rc in needs_action:
                self._maybe_restart(name)
            self._stop.wait(interval)

    def _maybe_restart(self, name: str) -> None:
        with self._lock:
            cfg = self.bots[name]
            state = self.states[name]
            max_r = cfg.max_restarts if cfg.max_restarts is not None else self.settings["max_restarts"]
            if max_r is not None and state.restart_count >= max_r:
                self.log.error(
                    "Bot '%s' hit max_restarts=%d — giving up. "
                    "Use the dashboard to restart manually.", name, max_r,
                )
                self._notify_crash(name, f"gave up after {max_r} restarts")
                return
            state.restart_count += 1
            delay_base = (cfg.restart_delay_base if cfg.restart_delay_base is not None
                          else self.settings["restart_delay_base"])
            delay_max = self.settings["restart_delay_max"]
            # Exponential backoff capped at delay_max.
            delay = min(delay_base * (2 ** max(0, state.restart_count - 1)), delay_max)
            state.status = "restarting"
            self.log.info("Bot '%s' restarting in %.1fs (attempt %d)...",
                          name, delay, state.restart_count)
        # Sleep OUTSIDE the lock so other ops (stop, start, restart) can
        # proceed during the backoff window.
        if self._stop.wait(delay):
            return  # shutdown signaled
        with self._lock:
            # Re-check: someone might have stopped/disabled the bot while we slept.
            if self._stop.is_set():
                return
            cfg = self.bots[name]
            if not cfg.enabled:
                state = self.states[name]
                state.status = "disabled"
                return
            # If someone manually restarted/stopped while we slept, don't fight them.
            if self.states[name].status not in ("crashed", "restarting"):
                return
        self._start_one(name)

    def _notify_crash(self, name: str, reason: str) -> None:
        if self._notifier:
            try:
                self._notifier.notify_crash(name, reason)
            except Exception as exc:  # noqa: BLE001
                self.log.warning("webhook notify failed: %s", exc)


# ---------------------------------------------------------------------------
# 6. Webhook notifier
# ---------------------------------------------------------------------------
class WebhookNotifier:
    """Sends crash alerts to Slack / Discord / generic HTTP webhook.

    The notifier is best-effort: a failed webhook delivery is logged but
    never raises — alerting must never block the supervisor.
    """

    def __init__(self, url: str, timeout: float = 5.0):
        self.url = url
        self.timeout = timeout
        self.log = logging.getLogger("multibots.webhook")

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    def notify_crash(self, bot_name: str, reason: str) -> bool:
        if not self.enabled:
            return False
        # Discord/Slack both accept {"content": "..."} or {"text": "..."}.
        # Send both keys for max compatibility.
        payload = {
            "text": f"⚠️ MultiBots: bot *{bot_name}* crashed — {reason}",
            "content": f"⚠️ MultiBots: bot **{bot_name}** crashed — {reason}",
            "username": "MultiBots",
            "bot_name": bot_name,
            "reason": reason,
            "ts": utc_now_iso(),
        }
        try:
            resp = requests.post(
                self.url, json=payload, timeout=self.timeout,
                headers={"User-Agent": f"MultiBots/{__version__}"},
            )
            if resp.status_code >= 400:
                self.log.warning("webhook returned HTTP %d: %s",
                                 resp.status_code, resp.text[:200])
                return False
            return True
        except requests.RequestException as exc:
            self.log.warning("webhook request failed: %s", exc)
            return False


# ---------------------------------------------------------------------------
# 7. Keep-alive pinger
# ---------------------------------------------------------------------------
class KeepAlivePinger(threading.Thread):
    """Pings the local web server to prevent free-host idling.

    Fixes two bugs in the original implementation:
      * Use ``127.0.0.1`` instead of ``0.0.0.0`` (the latter is a bind
        address, not a valid connect target on all platforms).
      * Wait for the Flask app to be reachable before starting the loop
        (the original fired immediately, racing the server startup).
    """

    def __init__(self, url: str, interval: float = 120.0):
        super().__init__(name="keepalive", daemon=True)
        self.url = url
        self.interval = interval
        self._stop = threading.Event()
        self.log = logging.getLogger("multibots.pinger")

    def run(self) -> None:
        # Wait (briefly) for the server to come up — max 30s.
        deadline = time.time() + 30.0
        while time.time() < deadline and not self._stop.is_set():
            try:
                if requests.get(self.url, timeout=2).status_code < 500:
                    break
            except requests.RequestException:
                time.sleep(1.0)
        while not self._stop.is_set():
            try:
                requests.get(self.url, timeout=5)
            except requests.RequestException as exc:
                self.log.debug("keep-alive ping failed: %s", exc)
            self._stop.wait(self.interval)

    def stop(self) -> None:
        self._stop.set()


# ---------------------------------------------------------------------------
# 8. Graceful shutdown
# ---------------------------------------------------------------------------
class GracefulShutdown:
    """Installs SIGTERM/SIGINT handlers that drain bots cleanly.

    Platforms like Render / Heroku / Kubernetes send SIGTERM before
    SIGKILL with a grace period (usually 30s). Without this handler,
    bot subprocesses become orphans and leak.
    """

    def __init__(self, supervisor: BotSupervisor, pinger: KeepAlivePinger,
                 metrics: MetricsCollector, timeout: float = 15.0):
        self.supervisor = supervisor
        self.pinger = pinger
        self.metrics = metrics
        self.timeout = timeout
        self._installed = False

    def install(self) -> None:
        if self._installed:
            return
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._handler)
        self._installed = True

    def _handler(self, signum, frame) -> None:  # noqa: ARG002
        log = logging.getLogger("multibots.shutdown")
        log.info("Received signal %s — draining bots (timeout=%.1fs)...",
                 signal.Signals(signum).name, self.timeout)
        try:
            self.pinger.stop()
            self.metrics.stop()
            self.supervisor.stop_all(timeout=self.timeout)
        except Exception as exc:  # noqa: BLE001
            log.error("error during shutdown: %s\n%s", exc, traceback.format_exc())
        log.info("Shutdown complete. Exiting.")
        # Use os._exit to bypass any non-daemon threads that might still
        # be running (e.g. a hung subprocess.wait()).
        os._exit(0)


# ---------------------------------------------------------------------------
# 9. Main entry point
# ---------------------------------------------------------------------------
class MultiBots:
    """Top-level orchestrator — wires all components together.

    The dashboard module imports this class to access the live
    supervisor; you should normally have exactly one ``MultiBots``
    instance per process.
    """

    def __init__(self, settings: Optional[Dict[str, Any]] = None,
                 log: Optional[logging.Logger] = None):
        self.settings = {**DEFAULTS, **(settings or {})}
        self.log = log or setup_logging(
            level=self.settings["log_level"],
            log_dir=self.settings["log_dir"],
            max_bytes=self.settings["log_max_bytes"],
            backup_count=self.settings["log_backup_count"],
        )
        self.loader = ConfigLoader(self.settings)
        self.bots: List[BotConfig] = []
        self.dashboard_cfg: Dict[str, Any] = {}
        self.supervisor: Optional[BotSupervisor] = None
        self.metrics: Optional[MetricsCollector] = None
        self.pinger: Optional[KeepAlivePinger] = None
        self.notifier: Optional[WebhookNotifier] = None
        self.shutdown_handler: Optional[GracefulShutdown] = None
        self._started = False

    def load_config(self) -> None:
        self.bots, self.dashboard_cfg = self.loader.load()
        self.log.info("Loaded %d bot(s) from %s",
                      len(self.bots), self.settings["config_path"])

    def build_components(self) -> None:
        if not self.bots:
            self.log.warning("No bots configured — supervisor will be idle.")
        self.supervisor = BotSupervisor(self.bots, self.settings)
        self.notifier = WebhookNotifier(
            self.settings["webhook_url"], self.settings["webhook_timeout"],
        )
        self.supervisor.attach_notifier(self.notifier)
        self.metrics = MetricsCollector(
            self.supervisor, history_size=self.settings["metrics_history"],
        )
        self.pinger = KeepAlivePinger(
            self.settings["ping_url"], self.settings["ping_interval"],
        )
        self.shutdown_handler = GracefulShutdown(
            self.supervisor, self.pinger, self.metrics,
            timeout=self.settings["shutdown_timeout"],
        )

    def start(self, run_pinger: bool = True, install_signals: bool = True) -> None:
        if self._started:
            self.log.warning("MultiBots.start() called twice — ignoring.")
            return
        self._started = True
        if not self.bots:
            self.load_config()
        if self.supervisor is None:
            self.build_components()
        if install_signals:
            self.shutdown_handler.install()
        # Start metrics first so we capture startup samples.
        self.metrics.start()
        self.supervisor.start_all()
        if run_pinger:
            self.pinger.start()
        self.log.info("MultiBots v%s started — %d bot(s) supervised.",
                      __version__, len(self.bots))

    def stop(self) -> None:
        if self.pinger:
            self.pinger.stop()
        if self.metrics:
            self.metrics.stop()
        if self.supervisor:
            self.supervisor.stop_all()


def main() -> int:
    """Console entry point — used when running ``python main.py`` directly.

    The supervisor itself doesn't serve HTTP; that's the dashboard's job.
    If the dashboard is disabled, we still run the keep-alive pinger
    against an external URL (set ``MB_PING_URL``) so free hosts don't
    sleep the container.
    """
    settings = dict(DEFAULTS)
    mb = MultiBots(settings=settings)
    mb.start(run_pinger=True, install_signals=True)

    # Block forever — the supervisor + watchdog + pinger are daemons.
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        mb.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
