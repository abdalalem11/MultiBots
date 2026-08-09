"""
MultiBots — Git Source Downloader + Process Supervisor
========================================================
- Reads config.json
- Clones each bot from "source" automatically
- Updates existing Git repositories with git pull
- Installs each bot requirements.txt automatically
- Runs the configured Python entry file
- Restarts crashed bots
- Works with Render / Docker / VPS
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

VERSION = "3.0.0"

BASE_DIR = Path(os.environ.get("MB_BASE_DIR", "/app"))
CONFIG_PATH = Path(os.environ.get("MB_CONFIG_PATH", str(BASE_DIR / "config.json")))

BOTS_DIR = Path(os.environ.get("MB_BOTS_DIR", str(BASE_DIR)))

LOG_LEVEL = os.environ.get("MB_LOG_LEVEL", "INFO").upper()

START_DELAY = float(os.environ.get("MB_START_DELAY", "2"))
RESTART_DELAY = float(os.environ.get("MB_RESTART_DELAY", "5"))
MAX_RESTARTS = int(os.environ.get("MB_MAX_RESTARTS", "10"))

BOT_INSTALL_REQUIREMENTS = (
    os.environ.get("MB_INSTALL_BOT_REQUIREMENTS", "true").lower()
    in ("1", "true", "yes", "on")
)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
)

LOG = logging.getLogger("multibots")


# ---------------------------------------------------------------------------
# Bot configuration
# ---------------------------------------------------------------------------

@dataclass
class BotConfig:
    name: str
    source: str
    run: str
    env: Dict[str, str] = field(default_factory=dict)

    enabled: bool = True
    python: str = sys.executable
    args: List[str] = field(default_factory=list)

    max_restarts: Optional[int] = None
    restart_delay: Optional[float] = None

    cwd: Optional[str] = None

    def bot_dir(self) -> Path:
        if self.cwd:
            path = Path(self.cwd)

            if not path.is_absolute():
                path = BOTS_DIR / path

            return path

        return BOTS_DIR / self.name

    def run_file(self) -> Path:
        return self.bot_dir() / self.run


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

class ConfigLoader:

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> List[BotConfig]:

        if not self.path.exists():
            raise RuntimeError(
                f"config.json not found: {self.path}"
            )

        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            raise RuntimeError(
                f"Cannot read config.json: {exc}"
            )

        if not isinstance(data, dict):
            raise RuntimeError(
                "config.json must contain a JSON object"
            )

        bots = []

        for name, raw in data.items():

            if name.startswith("_"):
                continue

            if not isinstance(raw, dict):
                LOG.error(
                    "Skipping '%s': configuration must be an object",
                    name,
                )
                continue

            source = str(raw.get("source", "")).strip()
            run = str(raw.get("run", "")).strip()

            if not source:
                LOG.error(
                    "Skipping '%s': source is missing",
                    name,
                )
                continue

            if not run:
                LOG.error(
                    "Skipping '%s': run is missing",
                    name,
                )
                continue

            env = raw.get("env", {}) or {}

            if not isinstance(env, dict):
                LOG.error(
                    "Skipping '%s': env must be an object",
                    name,
                )
                continue

            env = {
                str(k): str(v)
                for k, v in env.items()
            }

            bots.append(
                BotConfig(
                    name=name,
                    source=source,
                    run=run,
                    env=env,
                    enabled=bool(
                        raw.get("enabled", True)
                    ),
                    python=str(
                        raw.get("python", sys.executable)
                    ),
                    args=[
                        str(x)
                        for x in raw.get("args", [])
                    ],
                    max_restarts=(
                        int(raw["max_restarts"])
                        if raw.get("max_restarts") is not None
                        else None
                    ),
                    restart_delay=(
                        float(raw["restart_delay"])
                        if raw.get("restart_delay") is not None
