"""
MultiBots - Multi-bot supervisor

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
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


__version__ = "2.2.2"


DEFAULTS: Dict[str, Any] = {
    "port": int(os.environ.get("MB_PORT", "10000")),
    "host": os.environ.get("MB_HOST", "0.0.0.0"),
    "bots_dir": os.environ.get("MB_BOTS_DIR", "/tmp/bots"),
    "config_path": os.environ.get("MB_CONFIG_PATH", "config.json"),
    "log_level": os.environ.get("MB_LOG_LEVEL", "INFO"),
    "start_delay": float(os.environ.get("MB_START_DELAY", "2")),
    "max_restarts": int(os.environ.get("MB_MAX_RESTARTS", "5")),
    "restart_delay_base": float(
        os.environ.get("MB_RESTART_DELAY_BASE", "2")
    ),
    "watchdog_interval": float(
        os.environ.get("MB_WATCHDOG_INTERVAL", "10")
    ),
    "shutdown_timeout": float(
        os.environ.get("MB_SHUTDOWN_TIMEOUT", "15")
    ),
}


_RESERVED_KEYS = {"_dashboard", "_global"}

_BOT_NAME_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_-]{0,63}$"
)

_REQUIRED_BOT_KEYS = {"source", "run"}


def setup_logging(level: str = "INFO") -> logging.Logger:
    logging.basicConfig(
        level=getattr(
            logging,
            level.upper(),
            logging.INFO,
        ),
        format=(
            "%(asctime)s %(levelname)-7s "
            "[%(name)s] %(message)s"
        ),
        stream=sys.stdout,
        force=True,
    )

    return logging.getLogger("multibots")


class ConfigError(Exception):
    pass


@dataclass
class BotConfig:
    name: str
    source: str
    run: str

    env: Dict[str, str] = field(default_factory=dict)

    enabled: bool = True

    max_restarts: Optional[int] = None

    restart_delay_base: Optional[float] = None

    cwd: Optional[str] = None

    python: str = field(
        default_factory=lambda: sys.executable
    )

    args: List[str] = field(
        default_factory=list
    )

    def resolve_cwd(self, bots_dir: str) -> str:
        if self.cwd:
            if os.path.isabs(self.cwd):
                return self.cwd

            return os.path.join(
                bots_dir,
                self.cwd,
            )

        return os.path.join(
            bots_dir,
            self.name,
        )

    def resolve_runfile(self, bots_dir: str) -> str:
        return os.path.join(
            self.resolve_cwd(bots_dir),
            self.run,
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
    ) -> List[BotConfig]:

        config_path = (
            path
            or self.settings["config_path"]
        )

        try:
            with open(
                config_path,
                "r",
                encoding="utf-8",
            ) as f:
                data = json.load(f)

        except FileNotFoundError as e:
            raise ConfigError(
                f"Config file not found: {config_path}"
            ) from e

        except json.JSONDecodeError as e:
            raise ConfigError(
                f"Invalid JSON in {config_path}: {e}"
            ) from e

        if isinstance(data, dict):
            bots_data = data.get(
                "bots",
                data,
            )
        else:
            bots_data = data

        if isinstance(bots_data, dict):

            items = []

            for name, value in bots_data.items():

                if name in _RESERVED_KEYS:
                    continue

                if isinstance(value, dict):

                    value = dict(value)

                    value.setdefault(
                        "name",
                        name,
                    )

                    items.append(value)

        elif isinstance(bots_data, list):

            items = bots_data

        else:
            raise ConfigError(
                "config.json must contain "
                "a list of bots or a bots object"
            )

        bots: List[BotConfig] = []

        for item in items:

            if not isinstance(
                item,
                dict,
            ):
                raise ConfigError(
                    "Each bot must be an object"
                )

            name = str(
                item.get(
                    "name",
                    "",
                )
            ).strip()

            if not _BOT_NAME_RE.match(name):
                raise ConfigError(
                    f"Invalid bot name: {name!r}"
                )

            missing = [
                key
                for key in _REQUIRED_BOT_KEYS
                if not item.get(key)
            ]

            if missing:
                raise ConfigError(
                    f"Bot {name}: missing "
                    f"{', '.join(missing)}"
                )

            bots.append(
                BotConfig(
                    name=name,

                    source=str(
                        item["source"]
                    ),

                    run=str(
                        item["run"]
                    ),

                    env={
                        str(k): str(v)
                        for k, v in dict(
                            item.get(
                                "env",
                                {},
                            )
                        ).items()
                    },

                    enabled=bool(
                        item.get(
                            "enabled",
                            True,
                        )
                    ),

                    max_restarts=item.get(
                        "max_restarts"
                    ),

                    restart_delay_base=item.get(
                        "restart_delay_base"
                    ),

                    cwd=item.get(
                        "cwd"
                    ),

                    python=str(
                        item.get(
                            "python",
                            sys.executable,
                        )
                    ),

                    args=[
                        str(x)
                        for x in item.get(
                            "args",
                            [],
                        )
                    ],
                )
            )

        return bots


class BotSupervisor:
    def __init__(
        self,
        config: BotConfig,
        settings: Dict[str, Any],
        logger: logging.Logger,
    ):

        self.config = config
        self.settings = settings
        self.logger = logger

        self.process: Optional[
            subprocess.Popen
        ] = None

        self.restarts = 0

    def download_source(self) -> None:

        target = Path(
            self.config.resolve_cwd(
                self.settings["bots_dir"]
            )
        )

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        source = self.config.source

        if source.startswith(
            (
                "http://",
                "https://",
            )
        ):

            if target.exists():
                shutil.rmtree(target)

            self.logger.info(
                "Cloning %s...",
                self.config.name,
            )

            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    source,
                    str(target),
                ],
                check=True,
            )

        else:

            src = Path(source)

            if not src.exists():
                raise FileNotFoundError(
                    f"Source not found: {source}"
                )

            if target.exists():
                shutil.rmtree(target)

            shutil.copytree(
                src,
                target,
            )

    def start(self) -> None:

        cwd = self.config.resolve_cwd(
            self.settings["bots_dir"]
        )

        runfile = self.config.resolve_runfile(
            self.settings["bots_dir"]
        )

        if not os.path.isfile(runfile):
            raise FileNotFoundError(
                f"Run file not found: {runfile}"
            )

        env = os.environ.copy()

        env.update(
            self.config.env
        )

        command = [
            self.config.python,
            runfile,
            *self.config.args,
        ]

        self.logger.info(
            "Starting %s: %s",
            self.config.name,
            " ".join(command),
        )

        self.process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
        )

        self.logger.info(
            "Started %s (pid=%s)",
            self.config.name,
            self.process.pid,
        )

    def stop(self) -> None:

        if (
            self.process
            and self.process.poll() is None
        ):

            self.logger.info(
                "Stopping %s",
                self.config.name,
            )

            self.process.terminate()

            try:
                self.process.wait(
                    timeout=self.settings[
                        "shutdown_timeout"
                    ]
                )

            except subprocess.TimeoutExpired:

                self.logger.warning(
                    "Force killing %s",
                    self.config.name,
                )

                self.process.kill()


class MultiBots:
    def __init__(
        self,
        settings: Optional[
            Dict[str, Any]
        ] = None,
    ):

        self.settings = dict(
            DEFAULTS
        )

        if settings:
            self.settings.update(
                settings
            )

        self.logger = setup_logging(
            self.settings["log_level"]
        )

        self.supervisors: List[
            BotSupervisor
        ] = []

        self.running = True

    def run(self) -> None:

        configs = ConfigLoader(
            self.settings
        ).load()

        if not configs:
            self.logger.warning(
                "No bots configured"
            )

        for config in configs:

            if not config.enabled:

                self.logger.info(
                    "Skipping disabled bot: %s",
                    config.name,
                )

                continue

            supervisor = BotSupervisor(
                config,
                self.settings,
                self.logger,
            )

            try:

                supervisor.download_source()
                supervisor.start()

            except Exception:

                self.logger.exception(
                    "Failed to start %s",
                    config.name,
                )

                continue

            self.supervisors.append(
                supervisor
            )

            time.sleep(
                self.settings[
                    "start_delay"
                ]
            )

        while self.running:

            for supervisor in self.supervisors:

                proc = supervisor.process

                if (
                    proc
                    and proc.poll() is not None
                ):

                    limit = (
                        supervisor.config.max_restarts
                    )

                    if limit is None:
                        limit = self.settings[
                            "max_restarts"
                        ]

                    if supervisor.restarts < limit:

                        supervisor.restarts += 1

                        delay = (
                            supervisor.config
                            .restart_delay_base
                        )

                        if delay is None:
                            delay = self.settings[
                                "restart_delay_base"
                            ]

                        self.logger.warning(
                            "Restarting %s "
                            "(attempt %s/%s)",
                            supervisor.config.name,
                            supervisor.restarts,
                            limit,
                        )

                        time.sleep(
                            float(delay)
                        )

                        try:
                            supervisor.start()

                        except Exception:

                            self.logger.exception(
                                "Failed to restart %s",
                                supervisor.config.name,
                            )

                    else:

                        self.logger.error(
                            "Restart limit reached "
                            "for %s",
                            supervisor.config.name,
                        )

            time.sleep(
                self.settings[
                    "watchdog_interval"
                ]
            )

    def shutdown(self) -> None:

        self.running = False

        for supervisor in self.supervisors:
            supervisor.stop()


def main() -> None:

    app = MultiBots()

    def handle_signal(
        signum,
        frame,
    ):

        app.shutdown()
        raise SystemExit(0)

    signal.signal(
        signal.SIGINT,
        handle_signal,
    )

    signal.signal(
        signal.SIGTERM,
        handle_signal,
    )

    app.run()


if __name__ == "__main__":
    main()
