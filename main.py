"""
MultiBots - Multi-bot supervisor
---------------------------------
Downloads bot sources from config.json automatically,
then starts and supervises each bot.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
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


__version__ = "2.1.0"

__all__ = [
    "BotConfig",
    "BotState",
    "BotSupervisor",
    "MetricsCollector",
    "ConfigLoader",
    "WebhookNotifier",
    "KeepAlivePinger",
    "GracefulShutdown",
    "MultiBots",
    "DEFAULTS",
    "setup_logging",
    "utc_now_iso",
]


# ============================================================================
# 1. DEFAULT SETTINGS
# ============================================================================

DEFAULTS: Dict[str, Any] = {
    "port": int(os.environ.get("MB_PORT", "10000")),
    "host": os.environ.get("MB_HOST", "0.0.0.0"),

    # Directory where downloaded bots are stored.
    "bots_dir": os.environ.get("MB_BOTS_DIR", "/app/bots"),

    "config_path": os.environ.get(
        "MB_CONFIG_PATH",
        "config.json",
    ),

    "log_level": os.environ.get(
        "MB_LOG_LEVEL",
        "INFO",
    ),

    "log_dir": os.environ.get(
        "MB_LOG_DIR",
        "logs",
    ),

    "log_max_bytes": int(
        os.environ.get(
            "MB_LOG_MAX_BYTES",
            str(5 * 1024 * 1024),
        )
    ),

    "log_backup_count": int(
        os.environ.get(
            "MB_LOG_BACKUP_COUNT",
            "5",
        )
    ),

    "start_delay": float(
        os.environ.get(
            "MB_START_DELAY",
            "2",
        )
    ),

    "max_restarts": int(
        os.environ.get(
            "MB_MAX_RESTARTS",
            "5",
        )
    ),

    "restart_delay_base": float(
        os.environ.get(
            "MB_RESTART_DELAY_BASE",
            "2",
        )
    ),

    "restart_delay_max": float(
        os.environ.get(
            "MB_RESTART_DELAY_MAX",
            "120",
        )
    ),

    "watchdog_interval": float(
        os.environ.get(
            "MB_WATCHDOG_INTERVAL",
            "10",
        )
    ),

    "ping_interval": float(
        os.environ.get(
            "MB_PING_INTERVAL",
            "120",
        )
    ),

    "ping_url": os.environ.get(
        "MB_PING_URL",
        "http://127.0.0.1:10000/",
    ),

    "webhook_url": os.environ.get(
        "MB_WEBHOOK_URL",
        "",
    ),

    "webhook_timeout": float(
        os.environ.get(
            "MB_WEBHOOK_TIMEOUT",
            "5",
        )
    ),

    "shutdown_timeout": float(
        os.environ.get(
            "MB_SHUTDOWN_TIMEOUT",
            "15",
        )
    ),

    "metrics_history": int(
        os.environ.get(
            "MB_METRICS_HISTORY",
            "180",
        )
    ),
}


_RESERVED_KEYS = {
    "_dashboard",
    "_global",
}


_BOT_NAME_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_-]{0,63}$"
)


_REQUIRED_BOT_KEYS = {
    "source",
    "run",
}


_OPTIONAL_BOT_KEYS: Dict[str, Any] = {
    "env": {},
    "enabled": True,
    "max_restarts": None,
    "restart_delay_base": None,
    "health_url": "",
    "health_timeout": 5.0,
    "cwd": None,
    "python": sys.executable,
    "args": [],
    "timeout_graceful": 10.0,
}


# ============================================================================
# 2. LOGGING
# ============================================================================

def utc_now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def setup_logging(
    level: str = "INFO",
    log_dir: Optional[str] = None,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.Logger:

    root = logging.getLogger()

    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s "
        "[%(name)s] %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(
        sys.stdout
    )

    console.setFormatter(formatter)

    root.addHandler(console)

    if log_dir:
        try:
            Path(log_dir).mkdir(
                parents=True,
                exist_ok=True,
            )

            from logging.handlers import RotatingFileHandler

            file_handler = RotatingFileHandler(
                Path(log_dir) / "multibots.log",
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )

            file_handler.setFormatter(
                formatter
            )

            root.addHandler(file_handler)

        except OSError:
            pass

    try:
        root.setLevel(
            level.upper()
        )
    except Exception:
        root.setLevel(
            logging.INFO
        )

    return logging.getLogger(
        "multibots"
    )


# ============================================================================
# 3. CONFIGURATION
# ============================================================================

class ConfigError(Exception):
    pass


@dataclass
class BotConfig:

    name: str
    source: str
    run: str

    env: Dict[str, str] = field(
        default_factory=dict
    )

    enabled: bool = True

    max_restarts: Optional[int] = None

    restart_delay_base: Optional[float] = None

    health_url: str = ""

    health_timeout: float = 5.0

    cwd: Optional[str] = None

    python: str = field(
        default_factory=lambda: sys.executable
    )

    args: List[str] = field(
        default_factory=list
    )

    timeout_graceful: float = 10.0

    def resolve_cwd(
        self,
        bots_dir: str,
    ) -> str:

        if self.cwd:
            if os.path.isabs(
                self.cwd
            ):
                return self.cwd

            return os.path.join(
                bots_dir,
                self.cwd,
            )

        return os.path.join(
            bots_dir,
            self.name,
        )

    def resolve_runfile(
        self,
        bots_dir: str,
    ) -> str:

        return os.path.join(
            self.resolve_cwd(
                bots_dir
            ),
            self.run,
        )

    def to_public_dict(
        self,
    ) -> Dict[str, Any]:

        return {
            "name": self.name,
            "source": self.source,
            "run": self.run,
            "enabled": self.enabled,
            "max_restarts": self.max_restarts,
            "restart_delay_base": self.restart_delay_base,
            "health_url": self.health_url,
            "has_env": bool(self.env),
            "env_keys": sorted(
                self.env.keys()
            ),
            "cwd": self.cwd,
            "args": list(self.args),
            "python": self.python,
        }


def _mask(
    value: str,
    visible: int = 4,
) -> str:

    if not value:
        return ""

    if len(value) <= visible * 2:
        return "*" * len(value)

    return (
        value[:visible]
        + "…"
        + value[-visible:]
    )


class ConfigLoader:

    def __init__(
        self,
        settings: Dict[str, Any],
    ):

        self.settings = settings

    def load(
        self,
        path: Optional[str] = None,
