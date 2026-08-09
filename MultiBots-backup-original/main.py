import json
import os
import subprocess
import threading
import time

import requests
from flask import Flask

app = Flask(__name__)


@app.route("/")
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MultiBots</title>
        <style>
            body {
                background: antiquewhite;
                text-align: center;
                padding-top: 50px;
                font-family: Arial, sans-serif;
            }
            img {
                max-width: 90%;
                border-radius: 12px;
            }
        </style>
    </head>
    <body>
        <img src="https://i.giphy.com/media/3o7abAHdYvZdBNnGZq/giphy.webp">
        <h2>MultiBots is running</h2>
    </body>
    </html>
    """


@app.route("/healthz")
def healthz():
    return "OK", 200


def keep_alive():
    """
    Keeps the web service responsive.
    Render already handles the HTTP service, so this is only
    a lightweight periodic request.
    """
    while True:
        try:
            requests.get(
                "http://127.0.0.1:10000/healthz",
                timeout=10,
            )
        except Exception:
            pass

        time.sleep(120)


def run_bots():
    """
    Load bots from config.json and start each bot.
    """

    if not os.path.exists("config.json"):
        print("ERROR: config.json not found.")
        return

    try:
        with open("config.json", "r", encoding="utf-8") as file:
            bots = json.load(file)
    except Exception as exc:
        print(f"ERROR: failed to read config.json: {exc}")
        return

    processes = []

    for bot_name, bot_config in bots.items():

        if bot_name.startswith("_"):
            continue

        if not bot_config.get("enabled", True):
            print(f"[{bot_name}] disabled.")
            continue

        bot_dir = os.path.join(os.getcwd(), bot_name)

        if not os.path.isdir(bot_dir):
            print(f"[{bot_name}] ERROR: directory not found: {bot_dir}")
            continue

        run_file = bot_config.get("run")

        if not run_file:
            print(f"[{bot_name}] ERROR: 'run' is missing in config.json")
            continue

        bot_file = os.path.join(bot_dir, run_file)

        if not os.path.isfile(bot_file):
            print(f"[{bot_name}] ERROR: run file not found: {bot_file}")
            continue

        bot_env = os.environ.copy()

        for env_name, env_value in bot_config.get("env", {}).items():
            bot_env[str(env_name)] = str(env_value)

        print(f"[{bot_name}] Starting: {bot_file}")

        try:
            process = subprocess.Popen(
                ["python", run_file],
                cwd=bot_dir,
                env=bot_env,
            )

            processes.append((bot_name, process))

        except Exception as exc:
            print(f"[{bot_name}] ERROR starting bot: {exc}")

        time.sleep(5)

    while True:
        for bot_name, process in processes:

            return_code = process.poll()

            if return_code is not None:
                print(
                    f"[{bot_name}] stopped "
                    f"(exit={return_code}). Restarting..."
                )

                try:
                    bot_config = bots[bot_name]
                    bot_dir = os.path.join(os.getcwd(), bot_name)
                    run_file = bot_config["run"]

                    bot_env = os.environ.copy()

                    for env_name, env_value in bot_config.get(
                        "env", {}
                    ).items():
                        bot_env[str(env_name)] = str(env_value)

                    new_process = subprocess.Popen(
                        ["python", run_file],
                        cwd=bot_dir,
                        env=bot_env,
                    )

                    processes[
                        processes.index((bot_name, process))
                    ] = (bot_name, new_process)

                except Exception as exc:
                    print(
                        f"[{bot_name}] restart failed: {exc}"
                    )

        time.sleep(2)


if __name__ == "__main__":

    threading.Thread(
        target=run_bots,
        daemon=True,
    ).start()

    threading.Thread(
        target=keep_alive,
        daemon=True,
    ).start()

    port = int(os.environ.get("PORT", "10000"))

    print(f"Web server listening on 0.0.0.0:{port}")

    app.run(
        host="0.0.0.0",
        port=port,
        threaded=True,
    )
