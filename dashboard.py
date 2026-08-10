"""
MultiBots Dashboard
Compatible with main.py v4.x

This dashboard imports only objects that actually exist in main.py.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, List

from flask import Flask, jsonify

from main import (
    DEFAULTS,
    BotSupervisor,
    ConfigLoader,
    MultiBots,
    setup_logging,
)


__version__ = "4.0.0"


# ============================================================
# LOGGING
# ============================================================

logger = setup_logging(
    os.environ.get(
        "MB_LOG_LEVEL",
        DEFAULTS.get("log_level", "INFO"),
    )
)


# ============================================================
# APPLICATION
# ============================================================

app = Flask(__name__)

# MultiBots supervisor instance
multibots = MultiBots()


# ============================================================
# HELPERS
# ============================================================

def get_status() -> List[Dict[str, Any]]:
    """
    Return the current status of all supervised bots.
    """

    try:
        return multibots.status()

    except Exception:
        logger.exception(
            "Failed to get MultiBots status"
        )

        return []


def build_response(
    status: str = "ok",
    **extra: Any,
) -> Dict[str, Any]:

    response: Dict[str, Any] = {
        "status": status,
        "service": "MultiBots",
        "version": __version__,
        "bots": get_status(),
    }

    response.update(extra)

    return response


# ============================================================
# ROUTES
# ============================================================

@app.get("/")
def index():
    """
    Main dashboard endpoint.
    """

    return jsonify(
        build_response(
            status="running"
        )
    )


@app.get("/health")
def health():
    """
    Render health-check endpoint.
    """

    return jsonify(
        build_response(
            status="ok"
        )
    )


@app.get("/status")
def status():
    """
    Detailed bot status.
    """

    bots = get_status()

    alive = sum(
        1
        for bot in bots
        if bot.get("alive")
    )

    return jsonify(
        build_response(
            total_bots=len(bots),
            alive_bots=alive,
            dead_bots=len(bots) - alive,
        )
    )


@app.get("/config")
def config():
    """
    Shows loaded bot configuration names.

    Sensitive environment values are not exposed.
    """

    try:

        configs = ConfigLoader(
            DEFAULTS
        ).load()

        result = []

        for bot in configs:

            result.append(
                {
                    "name": bot.name,
                    "source": bot.source,
                    "run": bot.run,
                    "enabled": bot.enabled,
                    "cwd": bot.cwd,
                    "python": bot.python,
                    "args": bot.args,
                    "max_restarts": bot.max_restarts,
                    "restart_delay_base": (
                        bot.restart_delay_base
                    ),
                }
            )

        return jsonify(
            {
                "status": "ok",
                "count": len(result),
                "bots": result,
            }
        )

    except Exception as exc:

        logger.exception(
            "Failed to load configuration"
        )

        return jsonify(
            {
                "status": "error",
                "error": str(exc),
            }
        ), 500


@app.get("/version")
def version():
    """
    Version information.
    """

    return jsonify(
        {
            "service": "MultiBots",
            "version": __version__,
        }
    )


# ============================================================
# START MULTIBOTS
# ============================================================

def start_multibots() -> None:
    """
    Start the MultiBots supervisor in the background.

    Gunicorn owns the HTTP server, so MultiBots runs
    separately from Flask.
    """

    def runner():

        try:

            logger.info(
                "Starting MultiBots supervisor..."
            )

            multibots.run()

        except Exception:

            logger.exception(
                "MultiBots supervisor crashed"
            )

    thread = threading.Thread(
        target=runner,
        name="multibots-supervisor",
        daemon=True,
    )

    thread.start()

    logger.info(
        "MultiBots supervisor thread started"
    )


# ============================================================
# GUNICORN ENTRYPOINT
# ============================================================

# Start the supervisor when dashboard.py is imported
# by Gunicorn.
start_multibots()


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":

    host = DEFAULTS.get(
        "host",
        "0.0.0.0",
    )

    port = int(
        os.environ.get(
            "PORT",
            DEFAULTS.get(
                "port",
                10000,
            ),
        )
    )

    logger.info(
        "Starting dashboard on %s:%s",
        host,
        port,
    )

    app.run(
        host=host,
        port=port,
        debug=False,
        use_reloader=False,
    )
