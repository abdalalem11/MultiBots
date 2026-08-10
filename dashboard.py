"""
MultiBots Dashboard
-------------------
Dashboard compatible with main.py v4.0.0

Works with:
    gunicorn dashboard:app

It starts the MultiBots supervisor in a background thread and
provides HTTP endpoints for Render health checks and monitoring.

Required:
    Flask
    gunicorn
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict

from flask import Flask, jsonify


# ============================================================
# APP
# ============================================================

app = Flask("multibots-dashboard")


# ============================================================
# LOGGING
# ============================================================

LOG_LEVEL = os.environ.get(
    "MB_LOG_LEVEL",
    "INFO",
).upper()

logging.basicConfig(
    level=getattr(
        logging,
        LOG_LEVEL,
        logging.INFO,
    ),
    format=(
        "%(asctime)s %(levelname)-7s "
        "[%(name)s] %(message)s"
    ),
)

logger = logging.getLogger("dashboard")


# ============================================================
# MULTIBOTS IMPORT
# ============================================================

try:
    from main import (
        DEFAULTS,
        MultiBots,
    )

except Exception as exc:
    DEFAULTS = {}
    MultiBots = None

    logger.exception(
        "Failed to import MultiBots from main.py: %s",
        exc,
    )


# ============================================================
# GLOBAL SUPERVISOR
# ============================================================

multibots = None

supervisor_thread = None

startup_error = None

started = False

startup_lock = threading.Lock()


# ============================================================
# SETTINGS
# ============================================================

def build_settings() -> Dict[str, Any]:
    """
    Build settings for MultiBots.

    Environment variables are read by main.py's DEFAULTS,
    but we also pass the important dashboard settings here
    explicitly.
    """

    settings = {}

    if isinstance(DEFAULTS, dict):
        settings.update(DEFAULTS)

    # Render provides PORT.
    settings["port"] = int(
        os.environ.get(
            "PORT",
            os.environ.get(
                "MB_PORT",
                str(settings.get("port", 10000)),
            ),
        )
    )

    settings["host"] = os.environ.get(
        "MB_HOST",
        settings.get(
            "host",
            "0.0.0.0",
        ),
    )

    settings["bots_dir"] = os.environ.get(
        "MB_BOTS_DIR",
        settings.get(
            "bots_dir",
            "/tmp/bots",
        ),
    )

    settings["config_path"] = os.environ.get(
        "MB_CONFIG_PATH",
        settings.get(
            "config_path",
            "config.json",
        ),
    )

    settings["log_level"] = os.environ.get(
        "MB_LOG_LEVEL",
        settings.get(
            "log_level",
            "INFO",
        ),
    )

    settings["start_delay"] = float(
        os.environ.get(
            "MB_START_DELAY",
            settings.get(
                "start_delay",
                2,
            ),
        )
    )

    settings["max_restarts"] = int(
        os.environ.get(
            "MB_MAX_RESTARTS",
            settings.get(
                "max_restarts",
                5,
            ),
        )
    )

    settings["restart_delay_base"] = float(
        os.environ.get(
            "MB_RESTART_DELAY_BASE",
            settings.get(
                "restart_delay_base",
                5,
            ),
        )
    )

    settings["watchdog_interval"] = float(
        os.environ.get(
            "MB_WATCHDOG_INTERVAL",
            settings.get(
                "watchdog_interval",
                10,
            ),
        )
    )

    settings["shutdown_timeout"] = float(
        os.environ.get(
            "MB_SHUTDOWN_TIMEOUT",
            settings.get(
                "shutdown_timeout",
                15,
            ),
        )
    )

    install_requirements = os.environ.get(
        "MB_INSTALL_REQUIREMENTS",
    )

    if install_requirements is not None:
        settings["install_requirements"] = (
            install_requirements.lower()
            not in {
                "0",
                "false",
                "no",
                "off",
            }
        )

    return settings


# ============================================================
# SUPERVISOR THREAD
# ============================================================

def supervisor_worker() -> None:
    global startup_error

    if MultiBots is None:
        startup_error = (
            "Could not import MultiBots from main.py"
        )
        return

    try:
        settings = build_settings()

        logger.info(
            "Starting MultiBots supervisor..."
        )

        logger.info(
            "Config path: %s",
            settings.get("config_path"),
        )

        logger.info(
            "Bots directory: %s",
            settings.get("bots_dir"),
        )

        global multibots

        multibots = MultiBots(
            settings=settings,
        )

        multibots.run()

    except Exception as exc:
        startup_error = str(exc)

        logger.exception(
            "MultiBots supervisor crashed"
        )


# ============================================================
# START SUPERVISOR
# ============================================================

def start_supervisor() -> None:
    global supervisor_thread
    global started

    with startup_lock:

        if started:
            return

        started = True

        supervisor_thread = threading.Thread(
            target=supervisor_worker,
            name="multibots-supervisor",
            daemon=True,
        )

        supervisor_thread.start()

        logger.info(
            "MultiBots supervisor thread started"
        )


# ============================================================
# HELPERS
# ============================================================

def get_bot_status():
    """
    Return current bot status.

    Compatible with main.py:
        MultiBots.status()
    """

    if multibots is None:
        return []

    try:
        return multibots.status()

    except Exception as exc:
        logger.exception(
            "Failed to read bot status"
        )

        return [
            {
                "error": str(exc),
            }
        ]


def supervisor_alive() -> bool:
    return bool(
        supervisor_thread
        and supervisor_thread.is_alive()
    )


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def index():
    """
    Main dashboard endpoint.
    """

    bots = get_bot_status()

    alive = supervisor_alive()

    return jsonify(
        {
            "service": "MultiBots",
            "version": "4.0.0",
            "status": (
                "running"
                if alive
                else "starting"
            ),
            "supervisor_alive": alive,
            "startup_error": startup_error,
            "bot_count": len(bots),
            "bots": bots,
            "endpoints": {
                "health": "/health",
                "healthz": "/healthz",
                "status": "/status",
            },
        }
    )


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():
    """
    Human/API health endpoint.
    """

    bots = get_bot_status()

    alive_bots = sum(
        1
        for bot in bots
        if bot.get("alive") is True
    )

    return jsonify(
        {
            "status": "ok",
            "service": "MultiBots",
            "supervisor_alive": supervisor_alive(),
            "bots": {
                "total": len(bots),
                "alive": alive_bots,
            },
        }
    )


# ============================================================
# RENDER HEALTHCHECK
# ============================================================

@app.get("/healthz")
def healthz():
    """
    Endpoint used by Docker HEALTHCHECK and Render.
    """

    if startup_error:
        return jsonify(
            {
                "status": "error",
                "error": startup_error,
            }
        ), 503

    return jsonify(
        {
            "status": "ok",
        }
    ), 200


# ============================================================
# STATUS
# ============================================================

@app.get("/status")
def status():
    """
    Detailed supervisor and bot status.
    """

    bots = get_bot_status()

    return jsonify(
        {
            "service": "MultiBots",
            "version": "4.0.0",
            "supervisor": {
                "alive": supervisor_alive(),
                "started": started,
                "error": startup_error,
            },
            "bots": bots,
        }
    )


# ============================================================
# PING
# ============================================================

@app.get("/ping")
def ping():
    return jsonify(
        {
            "status": "pong",
            "service": "MultiBots",
        }
    )


# ============================================================
# STARTUP
# ============================================================

def initialize() -> None:
    """
    Start the supervisor exactly once.

    Gunicorn can load this module in multiple workers.
    Each worker gets its own process, so avoid starting
    duplicate supervisors inside the same process.
    """

    start_supervisor()


# ============================================================
# INITIALIZE ON IMPORT
# ============================================================

initialize()


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            os.environ.get(
                "MB_PORT",
                "10000",
            ),
        )
    )

    host = os.environ.get(
        "MB_HOST",
        "0.0.0.0",
    )

    logger.info(
        "Starting development dashboard on %s:%s",
        host,
        port,
    )

    app.run(
        host=host,
        port=port,
        debug=False,
        use_reloader=False,
    )
