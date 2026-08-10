"""
MultiBots Dashboard
-------------------
Dashboard compatible with main.py v4.0.0

Uses:
    - MultiBots.status()
    - BotSupervisor
    - ConfigLoader
    - DEFAULTS

No dependency on:
    KeepAlivePinger
    MetricsCollector
    WebhookNotifier
    utc_now_iso
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, render_template_string

from main import (
    DEFAULTS,
    BotSupervisor,
    ConfigLoader,
    MultiBots,
    setup_logging,
)


__version__ = "4.0.0"


# ============================================================
# SETTINGS
# ============================================================

HOST = os.environ.get(
    "DASHBOARD_HOST",
    DEFAULTS.get("host", "0.0.0.0"),
)

PORT = int(
    os.environ.get(
        "PORT",
        str(DEFAULTS.get("port", 10000)),
    )
)


# ============================================================
# APP
# ============================================================

app = Flask(__name__)

logger = setup_logging(
    os.environ.get(
        "MB_LOG_LEVEL",
        "INFO",
    )
)


# ============================================================
# MULTIBOTS INSTANCE
# ============================================================

multibots: Optional[MultiBots] = None


def get_multibots() -> MultiBots:
    global multibots

    if multibots is None:
        multibots = MultiBots()

    return multibots


# ============================================================
# HELPERS
# ============================================================

def get_bot_status() -> List[Dict[str, Any]]:
    """
    Returns the current bot status using the exact
    status() method provided by main.py.
    """

    try:
        return get_multibots().status()

    except Exception as exc:
        logger.exception(
            "Failed to read bot status: %s",
            exc,
        )

        return []


def get_configured_bots() -> List[Dict[str, Any]]:
    """
    Reads config.json and returns safe dashboard data.
    """

    try:

        configs = ConfigLoader(
            DEFAULTS
        ).load()

    except Exception as exc:

        logger.exception(
            "Failed to load config: %s",
            exc,
        )

        return []

    result = []

    for config in configs:

        result.append(
            {
                "name": config.name,
                "source": config.source,
                "run": config.run,
                "enabled": config.enabled,
                "cwd": config.cwd,
                "python": config.python,
                "args": config.args,
                "max_restarts": config.max_restarts,
                "restart_delay_base": (
                    config.restart_delay_base
                ),
            }
        )

    return result


def get_bot_files(
    bot_name: str,
) -> List[str]:

    bots_dir = Path(
        DEFAULTS["bots_dir"]
    )

    root = bots_dir / bot_name

    if not root.exists():
        return []

    if not root.is_dir():
        return []

    ignored = {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        "node_modules",
    }

    files = []

    try:

        for path in root.rglob("*"):

            relative = path.relative_to(root)

            if any(
                part in ignored
                for part in relative.parts
            ):
                continue

            if path.is_file():
                files.append(
                    str(relative)
                )

    except Exception as exc:

        logger.exception(
            "Failed to inspect %s: %s",
            bot_name,
            exc,
        )

    return sorted(files)


# ============================================================
# API
# ============================================================

@app.get("/api")
def api_index():

    return jsonify(
        {
            "service": "MultiBots Dashboard",
            "version": __version__,
            "status": "running",
            "bots": get_bot_status(),
        }
    )


@app.get("/api/health")
def api_health():

    statuses = get_bot_status()

    alive = [
        bot
        for bot in statuses
        if bot.get("alive")
    ]

    return jsonify(
        {
            "status": "ok",
            "service": "MultiBots",
            "version": __version__,
            "total": len(statuses),
            "alive": len(alive),
            "bots": statuses,
        }
    )


@app.get("/api/status")
def api_status():

    return jsonify(
        {
            "bots": get_bot_status(),
        }
    )


@app.get("/api/config")
def api_config():

    return jsonify(
        {
            "bots": get_configured_bots(),
        }
    )


@app.get("/api/bots/<bot_name>/files")
def api_bot_files(bot_name: str):

    return jsonify(
        {
            "bot": bot_name,
            "files": get_bot_files(
                bot_name
            ),
        }
    )


# ============================================================
# DASHBOARD HTML
# ============================================================

HTML = r"""
<!DOCTYPE html>

<html lang="ar" dir="rtl">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>MultiBots Dashboard</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family:
        Arial,
        Tahoma,
        sans-serif;

    background:
        #0b0f19;

    color:
        #ffffff;
}

.container {
    width: min(
        1200px,
        calc(100% - 30px)
    );

    margin:
        30px auto;
}

.header {
    display: flex;
    justify-content: space-between;
    align-items: center;

    gap: 20px;

    margin-bottom: 25px;
}

.title {
    font-size: 28px;
    font-weight: 800;
}

.subtitle {
    margin-top: 7px;
    color: #8d96a8;
    font-size: 14px;
}

.refresh {
    border: 0;
    padding: 12px 18px;
    border-radius: 12px;

    background: #1b2333;
    color: white;

    cursor: pointer;
}

.refresh:hover {
    background: #263149;
}

.cards {
    display: grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(
                180px,
                1fr
            )
        );

    gap: 15px;

    margin-bottom: 25px;
}

.card {
    background: #121927;

    border:
        1px solid #202a3d;

    border-radius: 18px;

    padding: 20px;
}

.card-title {
    color: #8d96a8;
    font-size: 14px;
}

.card-value {
    margin-top: 10px;

    font-size: 30px;
    font-weight: 800;
}

.table-wrapper {
    overflow-x: auto;

    background: #121927;

    border:
        1px solid #202a3d;

    border-radius: 18px;
}

table {
    width: 100%;
    border-collapse: collapse;
}

th,
td {
    padding: 16px;

    text-align: right;

    border-bottom:
        1px solid #202a3d;
}

th {
    color: #8d96a8;
    font-size: 13px;
}

td {
    font-size: 14px;
}

.status {
    display: inline-flex;

    align-items: center;

    gap: 7px;

    padding:
        6px 10px;

    border-radius:
        999px;

    font-size: 12px;
    font-weight: 700;
}

.online {
    background: #123b2b;
    color: #5ff0a5;
}

.offline {
    background: #3c1820;
    color: #ff7d91;
}

.disabled {
    background: #302c16;
    color: #e8d36d;
}

.dot {
    width: 8px;
    height: 8px;

    border-radius: 50%;

    background: currentColor;
}

.entry {
    direction: ltr;

    text-align: left;

    font-family:
        monospace;

    color: #9fc4ff;
}

.footer {
    margin-top: 20px;

    color: #687286;

    font-size: 12px;

    text-align: center;
}

.empty {
    padding: 35px;

    text-align: center;

    color: #8d96a8;
}

@media (max-width: 650px) {

    .header {
        align-items: stretch;
        flex-direction: column;
    }

    .refresh {
        width: 100%;
    }

    th,
    td {
        padding: 12px 10px;
    }

}

</style>

</head>


<body>

<div class="container">

    <div class="header">

        <div>

            <div class="title">
                MultiBots Dashboard
            </div>

            <div class="subtitle">
                مراقبة البوتات وحالتها بشكل مباشر
            </div>

        </div>

        <button
            class="refresh"
            onclick="loadData()"
        >
            تحديث
        </button>

    </div>


    <div class="cards">

        <div class="card">

            <div class="card-title">
                إجمالي البوتات
            </div>

            <div
                class="card-value"
                id="total"
            >
                -
            </div>

        </div>


        <div class="card">

            <div class="card-title">
                تعمل الآن
            </div>

            <div
                class="card-value"
                id="alive"
            >
                -
            </div>

        </div>


        <div class="card">

            <div class="card-title">
                متوقفة
            </div>

            <div
                class="card-value"
                id="offline"
            >
                -
            </div>

        </div>


        <div class="card">

            <div class="card-title">
                آخر تحديث
            </div>

            <div
                class="card-value"
                id="updated"
                style="font-size:18px"
            >
                -
            </div>

        </div>

    </div>


    <div class="table-wrapper">

        <table>

            <thead>

                <tr>

                    <th>
                        البوت
                    </th>

                    <th>
                        الحالة
                    </th>

                    <th>
                        PID
                    </th>

                    <th>
                        مرات إعادة التشغيل
                    </th>

                    <th>
                        Entry Point
                    </th>

                </tr>

            </thead>

            <tbody id="bots">

                <tr>

                    <td
                        colspan="5"
                        class="empty"
                    >
                        جاري التحميل...
                    </td>

                </tr>

            </tbody>

        </table>

    </div>


    <div class="footer">

        MultiBots v{{ version }}

    </div>

</div>


<script>

function escapeHtml(value) {

    if (value === null ||
        value === undefined) {

        return "";

    }

    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");

}


function statusHtml(bot) {

    if (bot.alive) {

        return `
            <span class="status online">
                <span class="dot"></span>
                يعمل
            </span>
        `;

    }

    return `
        <span class="status offline">
            <span class="dot"></span>
            متوقف
        </span>
    `;

}


function entryHtml(bot) {

    const entry = bot.entrypoint;

    if (!entry) {
        return "-";
    }

    if (Array.isArray(entry)) {

        return escapeHtml(
            entry[0] +
            ": " +
            entry[1]
        );

    }

    return escapeHtml(entry);

}


async function loadData() {

    try {

        const response =
            await fetch(
                "/api/status",
                {
                    cache: "no-store"
                }
            );

        if (!response.ok) {
            throw new Error(
                "HTTP " +
                response.status
            );
        }

        const data =
            await response.json();

        const bots =
            data.bots || [];


        const alive =
            bots.filter(
                bot => bot.alive
            ).length;


        const offline =
            bots.length -
            alive;


        document.getElementById(
            "total"
        ).textContent =
            bots.length;


        document.getElementById(
            "alive"
        ).textContent =
            alive;


        document.getElementById(
            "offline"
        ).textContent =
            offline;


        document.getElementById(
            "updated"
        ).textContent =
            new Date()
                .toLocaleTimeString(
                    "ar-SA"
                );


        const tbody =
            document.getElementById(
                "bots"
            );


        if (!bots.length) {

            tbody.innerHTML = `
                <tr>
                    <td
                        colspan="5"
                        class="empty"
                    >
                        لا توجد بوتات
                    </td>
                </tr>
            `;

            return;

        }


        tbody.innerHTML =
            bots.map(
                bot => `

                    <tr>

                        <td>
                            <strong>
                                ${escapeHtml(
                                    bot.name
                                )}
                            </strong>
                        </td>

                        <td>
                            ${statusHtml(bot)}
                        </td>

                        <td>
                            ${escapeHtml(
                                bot.pid ?? "-"
                            )}
                        </td>

                        <td>
                            ${escapeHtml(
                                bot.restarts ?? 0
                            )}
                        </td>

                        <td class="entry">
                            ${entryHtml(bot)}
                        </td>

                    </tr>

                `
            ).join("");

    } catch (error) {

        console.error(error);

        document.getElementById(
            "bots"
        ).innerHTML = `
            <tr>
                <td
                    colspan="5"
                    class="empty"
                >
                    تعذر الاتصال بالخادم
                </td>
            </tr>
        `;

    }

}


loadData();


setInterval(
    loadData,
    5000
);

</script>

</body>

</html>
"""


# ============================================================
# DASHBOARD ROUTE
# ============================================================

@app.get("/")
def dashboard():

    return render_template_string(
        HTML,
        version=__version__,
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    logger.info(
        "Starting MultiBots Dashboard"
    )

    logger.info(
        "Dashboard listening on %s:%s",
        HOST,
        PORT,
    )

    app.run(
        host=HOST,
        port=PORT,
        debug=False,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()
