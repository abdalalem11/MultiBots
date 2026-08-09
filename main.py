"""
MultiBots - Multi-bot supervisor
---------------------------------
Downloads bot sources from config.json automatically,
prints the downloaded bot tree, discovers the correct
entry point, then starts and supervises each bot.
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
from typing import Any, Dict, List, Optional, Tuple


__version__ = "2.3.0"


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

_IGNORED_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
}


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

    env: Dict[str, str] = field(
        default_factory=dict
    )

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

    def resolve_cwd(
        self,
        bots_dir: str,
    ) -> str:

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

    def resolve_runfile(
        self,
        bots_dir: str,
    ) -> str:

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

        self.entrypoint: Optional[
            Tuple[str, str]
        ] = None

    # ---------------------------------------------------------
    # PRINT BOT DIRECTORY
    # ---------------------------------------------------------

    def print_tree(self) -> None:

        root = Path(
            self.config.resolve_cwd(
                self.settings["bots_dir"]
            )
        )

        self.logger.info(
            "========== BOT CONTENTS: %s ==========",
            root,
        )

        if not root.exists():

            self.logger.warning(
                "Bot directory does not exist: %s",
                root,
            )

            return

        if not root.is_dir():

            self.logger.warning(
                "Bot path is not a directory: %s",
                root,
            )

            return

        try:

            files = []

            for path in root.rglob("*"):

                relative = path.relative_to(root)

                if any(
                    part in _IGNORED_DIRS
                    for part in relative.parts
                ):
                    continue

                files.append(
                    (
                        str(relative),
                        path.is_dir(),
                    )
                )

            files.sort(
                key=lambda item: (
                    item[0].count(os.sep),
                    item[0].lower(),
                )
            )

            if not files:

                self.logger.info(
                    "Bot directory is empty."
                )

            for relative, is_dir in files:

                if is_dir:

                    self.logger.info(
                        "  [DIR ] %s/",
                        relative,
                    )

                else:

                    self.logger.info(
                        "  [FILE] %s",
                        relative,
                    )

        except Exception:

            self.logger.exception(
                "Failed to print bot contents"
            )

        self.logger.info(
            "=========================================="
        )

    # ---------------------------------------------------------
    # ENTRY POINT DISCOVERY
    # ---------------------------------------------------------

    def _normalise_run(self) -> str:

        run = self.config.run.strip()

        run = run.replace(
            "\\",
            "/",
        )

        while run.startswith("./"):
            run = run[2:]

        return run

    def _module_from_file(
        self,
        root: Path,
        file: Path,
    ) -> Optional[str]:

        try:

            relative = file.relative_to(root)

        except ValueError:

            return None

        if relative.suffix != ".py":
            return None

        parts = list(
            relative.with_suffix("").parts
        )

        if not parts:
            return None

        # Root main.py -> not a package module.
        if len(parts) == 1:
            return None

        # Every parent directory must be a package.
        current = root

        for part in parts[:-1]:

            current = current / part

            if not (
                current.is_dir()
                and (
                    current / "__init__.py"
                ).is_file()
            ):

                return None

        return ".".join(parts)

    def _find_package_main(
        self,
        root: Path,
    ) -> Optional[Tuple[str, str]]:

        candidates = []

        try:

            for file in root.rglob("main.py"):

                relative = file.relative_to(root)

                if any(
                    part in _IGNORED_DIRS
                    for part in relative.parts
                ):
                    continue

                module = self._module_from_file(
                    root,
                    file,
                )

                if module:

                    candidates.append(
                        (
                            str(file),
                            module,
                        )
                    )

        except Exception:

            self.logger.exception(
                "Error while searching package main"
            )

        candidates.sort(
            key=lambda item: (
                item[0].count(os.sep),
                item[0].lower(),
            )
        )

        if candidates:

            file, module = candidates[0]

            return (
                "module",
                module,
            )

        return None

    def discover_entrypoint(
        self,
    ) -> Tuple[str, str]:

        root = Path(
            self.config.resolve_cwd(
                self.settings["bots_dir"]
            )
        )

        requested = self._normalise_run()

        self.logger.info(
            "Requested run entry: %s",
            requested,
        )

        # -----------------------------------------------------
        # 1. Exact file
        # -----------------------------------------------------

        exact = root / requested

        if exact.is_file():

            self.logger.info(
                "Entry point selected: file -> %s",
                exact,
            )

            return (
                "file",
                str(exact),
            )

        # -----------------------------------------------------
        # 2. Add .py automatically
        # -----------------------------------------------------

        if not requested.endswith(".py"):

            py_file = root / (
                requested + ".py"
            )

            if py_file.is_file():

                self.logger.info(
                    "Entry point selected: file -> %s",
                    py_file,
                )

                return (
                    "file",
                    str(py_file),
                )

        # -----------------------------------------------------
        # 3. package/main
        # -----------------------------------------------------

        package_request = requested.replace(
            "/",
            ".",
        )

        if package_request.endswith(".py"):

            package_request = package_request[
                :-3
            ]

        module_file = root / (
            package_request.replace(
                ".",
                os.sep,
            )
            + ".py"
        )

        if module_file.is_file():

            module_parts = package_request.split(".")

            if len(module_parts) > 1:

                package_root = root

                valid_package = True

                for part in module_parts[:-1]:

                    package_root = (
                        package_root / part
                    )

                    if not (
                        package_root.is_dir()
                        and (
                            package_root
                            / "__init__.py"
                        ).is_file()
                    ):

                        valid_package = False
                        break

                if valid_package:

                    self.logger.info(
                        "Entry point selected: "
                        "module -> %s",
                        package_request,
                    )

                    return (
                        "module",
                        package_request,
                    )

        # -----------------------------------------------------
        # 4. Automatic root main.py
        # -----------------------------------------------------

        root_main = root / "main.py"

        if root_main.is_file():

            self.logger.info(
                "Requested entry not found. "
                "Automatically selected root main.py: %s",
                root_main,
            )

            return (
                "file",
                str(root_main),
            )

        # -----------------------------------------------------
        # 5. Common entry files
        # -----------------------------------------------------

        for filename in (
            "app.py",
            "bot.py",
            "run.py",
            "start.py",
            "server.py",
        ):

            candidate = root / filename

            if candidate.is_file():

                self.logger.info(
                    "Automatically selected entry point: %s",
                    candidate,
                )

                return (
                    "file",
                    str(candidate),
                )

        # -----------------------------------------------------
        # 6. Search package/main.py
        # -----------------------------------------------------

        package_main = self._find_package_main(
            root
        )

        if package_main:

            mode, value = package_main

            self.logger.info(
                "Automatically selected package entry: %s",
                value,
            )

            return (
                mode,
                value,
            )

        # -----------------------------------------------------
        # Nothing found
        # -----------------------------------------------------

        raise FileNotFoundError(
            "Could not determine bot entry point. "
            f"Requested={requested!r}, "
            f"root={root}"
        )

    # ---------------------------------------------------------
    # DOWNLOAD
    # ---------------------------------------------------------

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

        self.print_tree()

    # ---------------------------------------------------------
    # START
    # ---------------------------------------------------------

    def start(self) -> None:

        cwd = Path(
            self.config.resolve_cwd(
                self.settings["bots_dir"]
            )
        )

        if not cwd.is_dir():

            raise FileNotFoundError(
                f"Bot directory not found: {cwd}"
            )

        mode, entrypoint = (
            self.discover_entrypoint()
        )

        env = os.environ.copy()

        env.update(
            self.config.env
        )

        if mode == "file":

            command = [
                self.config.python,
                entrypoint,
                *self.config.args,
            ]

        else:

            command = [
                self.config.python,
                "-m",
                entrypoint,
                *self.config.args,
            ]

        self.entrypoint = (
            mode,
            entrypoint,
        )

        self.logger.info(
            "Starting %s",
            self.config.name,
        )

        self.logger.info(
            "Working directory: %s",
            cwd,
        )

        self.logger.info(
            "Entry type: %s",
            mode,
        )

        self.logger.info(
            "Entry point: %s",
            entrypoint,
        )

        self.logger.info(
            "Command: %s",
            " ".join(
                repr(str(x))
                for x in command
            ),
        )

        self.process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
        )

        self.logger.info(
            "Started %s (pid=%s)",
            self.config.name,
            self.process.pid,
        )

    # ---------------------------------------------------------
    # STOP
    # ---------------------------------------------------------

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

        try:

            configs = ConfigLoader(
                self.settings
            ).load()

        except ConfigError:

            self.logger.exception(
                "Configuration error"
            )

            return

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
