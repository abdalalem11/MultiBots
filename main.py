"""
MultiBots - Multi-bot supervisor
---------------------------------
Downloads bot sources from config.json automatically,
prints the downloaded bot tree, discovers the correct
entry point, supports Python package execution for
relative imports, and supervises each bot.
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


__version__ = "2.4.0"


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

    # =========================================================
    # PATH HELPERS
    # =========================================================

    def get_root(self) -> Path:

        return Path(
            self.config.resolve_cwd(
                self.settings["bots_dir"]
            )
        ).resolve()

    # =========================================================
    # PRINT TREE
    # =========================================================

    def print_tree(self) -> None:

        root = self.get_root()

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

    # =========================================================
    # NORMALISE RUN
    # =========================================================

    def _normalise_run(self) -> str:

        run = self.config.run.strip()

        run = run.replace(
            "\\",
            "/",
        )

        while run.startswith("./"):
            run = run[2:]

        return run

    # =========================================================
    # PACKAGE DETECTION
    # =========================================================

    def _has_relative_imports(
        self,
        file: Path,
    ) -> bool:

        try:

            text = file.read_text(
                encoding="utf-8",
                errors="ignore",
            )

        except Exception:

            return False

        patterns = (
            r"^\s*from\s+\.",
            r"^\s*from\s+\.\w+",
            r"^\s*import\s+\.",
        )

        for pattern in patterns:

            if re.search(
                pattern,
                text,
                re.MULTILINE,
            ):

                return True

        return False

    def _is_package_dir(
        self,
        directory: Path,
    ) -> bool:

        return (
            directory.is_dir()
            and (
                directory / "__init__.py"
            ).is_file()
        )

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

        if len(parts) == 1:
            return None

        current = root

        for part in parts[:-1]:

            current = current / part

            if not self._is_package_dir(
                current
            ):

                return None

        return ".".join(parts)

    # =========================================================
    # PACKAGE MAIN SEARCH
    # =========================================================

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

            return candidates[0][0], candidates[0][1]

        return None

    # =========================================================
    # ENTRY POINT DISCOVERY
    # =========================================================

    def discover_entrypoint(
        self,
    ) -> Tuple[str, str]:

        root = self.get_root()

        requested = self._normalise_run()

        self.logger.info(
            "Requested run entry: %s",
            requested,
        )

        # -----------------------------------------------------
        # Exact file
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
        # Add .py
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
        # Explicit module
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

                    if not self._is_package_dir(
                        package_root
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
        # Root main.py
        # -----------------------------------------------------

        root_main = root / "main.py"

        if root_main.is_file():

            # مهم:
            # إذا كان main.py يحتوي from . import
            # فلا يمكن تشغيله كملف مباشر.
            if self._has_relative_imports(
                root_main
            ):

                self.logger.info(
                    "Root main.py uses relative imports."
                )

                self.logger.info(
                    "Package-aware execution will be used."
                )

                return (
                    "package_root_main",
                    str(root_main),
                )

            self.logger.info(
                "Automatically selected root main.py: %s",
                root_main,
            )

            return (
                "file",
                str(root_main),
            )

        # -----------------------------------------------------
        # Common entry files
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

                if self._has_relative_imports(
                    candidate
                ):

                    self.logger.info(
                        "%s uses relative imports.",
                        filename,
                    )

                    return (
                        "package_root_main",
                        str(candidate),
                    )

                self.logger.info(
                    "Automatically selected entry point: %s",
                    candidate,
                )

                return (
                    "file",
                    str(candidate),
                )

        # -----------------------------------------------------
        # Search package/main.py
        # -----------------------------------------------------

        package_main = self._find_package_main(
            root
        )

        if package_main:

            file, module = package_main

            self.logger.info(
                "Automatically selected package entry: %s",
                module,
            )

            return (
                "module",
                module,
            )

        raise FileNotFoundError(
            "Could not determine bot entry point. "
            f"Requested={requested!r}, "
            f"root={root}"
        )

    # =========================================================
    # PREPARE PACKAGE
    # =========================================================

    def prepare_package_execution(
        self,
        root: Path,
    ) -> str:

        """
        Prepare a root project for:

            python -m <package>.main

        This is required for files containing:

            from . import *

        If the downloaded repository does not have a root
        __init__.py, create an empty one so Python can treat
        the repository directory as a package.
        """

        init_file = root / "__init__.py"

        if not init_file.exists():

            self.logger.warning(
                "No root __init__.py found."
            )

            self.logger.warning(
                "Creating empty package initializer: %s",
                init_file,
            )

            init_file.write_text(
                "# Auto-created by MultiBots\n",
                encoding="utf-8",
            )

        package_name = root.name

        if not re.match(
            r"^[A-Za-z_][A-Za-z0-9_]*$",
            package_name,
        ):

            # Python module names cannot contain '-'.
            safe_name = re.sub(
                r"[^A-Za-z0-9_]",
                "_",
                package_name,
            )

            if not safe_name:
                safe_name = "bot"

            self.logger.warning(
                "Directory name %r is not a valid "
                "Python package name.",
                package_name,
            )

            self.logger.warning(
                "Package execution cannot safely use "
                "that directory name: %s",
                safe_name,
            )

            raise RuntimeError(
                f"Invalid Python package directory name: "
                f"{package_name!r}"
            )

        return package_name

    # =========================================================
    # DOWNLOAD
    # =========================================================

    def download_source(self) -> None:

        target = self.get_root()

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

    # =========================================================
    # BUILD COMMAND
    # =========================================================

    def build_command(
        self,
        mode: str,
        entrypoint: str,
        cwd: Path,
        env: Dict[str, str],
    ) -> List[str]:

        python = self.config.python

        # -----------------------------------------------------
        # Normal Python file
        # -----------------------------------------------------

        if mode == "file":

            return [
                python,
                entrypoint,
                *self.config.args,
            ]

        # -----------------------------------------------------
        # Normal Python module
        # -----------------------------------------------------

        if mode == "module":

            return [
                python,
                "-m",
                entrypoint,
                *self.config.args,
            ]

        # -----------------------------------------------------
        # Root main.py with relative imports
        #
        # Example:
        #
        # /tmp/bots/bot1/main.py
        #
        # contains:
        #
        # from . import *
        #
        # Run as:
        #
        # python -m bot1.main
        #
        # with:
        #
        # PYTHONPATH=/tmp/bots
        # -----------------------------------------------------

        if mode == "package_root_main":

            package_name = self.prepare_package_execution(
                cwd
            )

            env["PYTHONPATH"] = os.pathsep.join(
                [
                    str(cwd.parent),
                    env.get("PYTHONPATH", ""),
                ]
                if env.get("PYTHONPATH")
                else [
                    str(cwd.parent)
                ]
            )

            module_name = (
                f"{package_name}."
                f"{Path(entrypoint).stem}"
            )

            self.logger.info(
                "Package name: %s",
                package_name,
            )

            self.logger.info(
                "Module name: %s",
                module_name,
            )

            self.logger.info(
                "PYTHONPATH: %s",
                env["PYTHONPATH"],
            )

            return [
                python,
                "-m",
                module_name,
                *self.config.args,
            ]

        raise RuntimeError(
            f"Unknown entry mode: {mode}"
        )

    # =========================================================
    # START
    # =========================================================

    def start(self) -> None:

        cwd = self.get_root()

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

        command = self.build_command(
            mode,
            entrypoint,
            cwd,
            env,
        )

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

    # =========================================================
    # STOP
    # =========================================================

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

                try:
                    self.process.wait(
                        timeout=5
                    )
                except subprocess.TimeoutExpired:
                    pass


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

    # =========================================================
    # RUN
    # =========================================================

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

        # =====================================================
        # WATCHDOG
        # =====================================================

        while self.running:

            for supervisor in self.supervisors:

                proc = supervisor.process

                if (
                    proc
                    and proc.poll() is not None
                ):

                    return_code = proc.returncode

                    self.logger.warning(
                        "%s exited with return code %s",
                        supervisor.config.name,
                        return_code,
                    )

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

    # =========================================================
    # SHUTDOWN
    # =========================================================

    def shutdown(self) -> None:

        if not self.running:
            return

        self.running = False

        self.logger.info(
            "Shutting down MultiBots..."
        )

        for supervisor in self.supervisors:

            try:

                supervisor.stop()

            except Exception:

                self.logger.exception(
                    "Error stopping %s",
                    supervisor.config.name,
                )


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

    try:

        app.run()

    except KeyboardInterrupt:

        app.shutdown()


if __name__ == "__main__":

    main()
