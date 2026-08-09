"""
MultiBots - Multi-bot supervisor
--------------------------------
Render-compatible version.

Features:
- Downloads bot sources from config.json
- Installs requirements.txt
- Detects bot entry point
- Starts and restarts bots
- Opens an HTTP port for Render
- Health endpoint: /
- Status endpoint: /status
- Runs the supervisor in a background thread

Version: 3.1.0
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

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, jsonify


__version__ = "3.1.0"


# ============================================================
# DEFAULT SETTINGS
# ============================================================

DEFAULTS: Dict[str, Any] = {
    # Render provides PORT automatically.
    "port": int(
        os.environ.get(
            "PORT",
            os.environ.get(
                "MB_PORT",
                "10000",
            ),
        )
    ),

    "host": os.environ.get(
        "MB_HOST",
        "0.0.0.0",
    ),

    "bots_dir": os.environ.get(
        "MB_BOTS_DIR",
        "/tmp/bots",
    ),

    "config_path": os.environ.get(
        "MB_CONFIG_PATH",
        "config.json",
    ),

    "log_level": os.environ.get(
        "MB_LOG_LEVEL",
        "INFO",
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

    "watchdog_interval": float(
        os.environ.get(
            "MB_WATCHDOG_INTERVAL",
            "10",
        )
    ),

    "shutdown_timeout": float(
        os.environ.get(
            "MB_SHUTDOWN_TIMEOUT",
            "15",
        )
    ),

    "install_requirements": os.environ.get(
        "MB_INSTALL_REQUIREMENTS",
        "true",
    ).lower()
    not in {
        "0",
        "false",
        "no",
        "off",
    },
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


_IGNORED_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
}


# ============================================================
# GLOBAL STATE
# ============================================================

app = Flask(__name__)

multibots_instance = None

supervisor_thread: Optional[
    threading.Thread
] = None


# ============================================================
# LOGGING
# ============================================================

def setup_logging(
    level: str = "INFO",
) -> logging.Logger:

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

    return logging.getLogger(
        "multibots"
    )


class ConfigError(Exception):
    pass


# ============================================================
# HTTP SERVER
# ============================================================

@app.route("/")
def home():

    return jsonify(
        {
            "service": "MultiBots",
            "status": "online",
            "version": __version__,
        }
    )


@app.route("/health")
def health():

    return jsonify(
        {
            "status": "ok",
            "service": "MultiBots",
            "version": __version__,
        }
    )


@app.route("/status")
def status():

    global multibots_instance

    bots = []

    if multibots_instance is not None:

        for supervisor in (
            multibots_instance.supervisors
        ):

            process = supervisor.process

            running = (
                process is not None
                and process.poll() is None
            )

            bots.append(
                {
                    "name": supervisor.config.name,
                    "running": running,
                    "pid": (
                        process.pid
                        if process is not None
                        else None
                    ),
                    "restarts": supervisor.restarts,
                    "entrypoint": supervisor.entrypoint,
                }
            )

    return jsonify(
        {
            "status": "ok",
            "version": __version__,
            "bots": bots,
        }
    )


# ============================================================
# BOT CONFIG
# ============================================================

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


# ============================================================
# CONFIG LOADER
# ============================================================

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
            or self.settings[
                "config_path"
            ]
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
                f"Config file not found: "
                f"{config_path}"
            ) from e

        except json.JSONDecodeError as e:

            raise ConfigError(
                f"Invalid JSON in "
                f"{config_path}: {e}"
            ) from e

        if isinstance(
            data,
            dict,
        ):

            bots_data = data.get(
                "bots",
                data,
            )

        else:

            bots_data = data

        if isinstance(
            bots_data,
            dict,
        ):

            items = []

            for name, value in (
                bots_data.items()
            ):

                if name in _RESERVED_KEYS:
                    continue

                if isinstance(
                    value,
                    dict,
                ):

                    value = dict(
                        value
                    )

                    value.setdefault(
                        "name",
                        name,
                    )

                    items.append(
                        value
                    )

        elif isinstance(
            bots_data,
            list,
        ):

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

            if not _BOT_NAME_RE.match(
                name
            ):

                raise ConfigError(
                    f"Invalid bot name: "
                    f"{name!r}"
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

            raw_env = item.get(
                "env",
                {},
            )

            if not isinstance(
                raw_env,
                dict,
            ):

                raise ConfigError(
                    f"Bot {name}: env must "
                    f"be an object"
                )

            raw_args = item.get(
                "args",
                [],
            )

            if not isinstance(
                raw_args,
                list,
            ):

                raise ConfigError(
                    f"Bot {name}: args must "
                    f"be a list"
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
                        for k, v
                        in raw_env.items()
                    },

                    enabled=bool(
                        item.get(
                            "enabled",
                            True,
                        )
                    ),

                    max_restarts=(
                        item.get(
                            "max_restarts"
                        )
                    ),

                    restart_delay_base=(
                        item.get(
                            "restart_delay_base"
                        )
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
                        for x in raw_args
                    ],
                )
            )

        return bots


# ============================================================
# BOT SUPERVISOR
# ============================================================

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

    # ========================================================
    # PATHS
    # ========================================================

    def get_root(self) -> Path:

        return Path(
            self.config.resolve_cwd(
                self.settings[
                    "bots_dir"
                ]
            )
        )

    # ========================================================
    # TREE
    # ========================================================

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

            entries = []

            for path in root.rglob("*"):

                relative = path.relative_to(
                    root
                )

                if any(
                    part in _IGNORED_DIRS
                    for part in relative.parts
                ):

                    continue

                entries.append(
                    (
                        str(relative),
                        path.is_dir(),
                    )
                )

            entries.sort(
                key=lambda x: (
                    x[0].count(
                        os.sep
                    ),
                    x[0].lower(),
                )
            )

            if not entries:

                self.logger.info(
                    "Bot directory is empty."
                )

            for relative, is_dir in entries:

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

    # ========================================================
    # NORMALISE RUN
    # ========================================================

    def _normalise_run(self) -> str:

        run = self.config.run.strip()

        run = run.replace(
            "\\",
            "/",
        )

        while run.startswith("./"):

            run = run[2:]

        return run

    # ========================================================
    # PYTHON FILE TEST
    # ========================================================

    def _is_python_file(
        self,
        path: Path,
    ) -> bool:

        return (
            path.is_file()
            and path.suffix.lower()
            == ".py"
        )

    # ========================================================
    # ENSURE INIT
    # ========================================================

    def _ensure_init_file(
        self,
        directory: Path,
    ) -> None:

        if not directory.is_dir():
            return

        init_file = (
            directory
            / "__init__.py"
        )

        if init_file.exists():
            return

        init_file.write_text(
            "",
            encoding="utf-8",
        )

        self.logger.info(
            "Created missing package file: %s",
            init_file,
        )

    # ========================================================
    # PREPARE PACKAGES
    # ========================================================

    def prepare_python_packages(
        self,
    ) -> None:

        root = self.get_root()

        if not root.is_dir():
            return

        self.logger.info(
            "Preparing Python package structure..."
        )

        self._ensure_init_file(
            root
        )

        for directory in root.rglob("*"):

            if not directory.is_dir():
                continue

            relative = directory.relative_to(
                root
            )

            if any(
                part in _IGNORED_DIRS
                for part in relative.parts
            ):

                continue

            try:

                has_python = any(
                    child.is_file()
                    and child.suffix.lower()
                    == ".py"
                    for child in directory.iterdir()
                )

            except OSError:

                continue

            if has_python:

                self._ensure_init_file(
                    directory
                )

        self.logger.info(
            "Python package preparation complete."
        )

    # ========================================================
    # RELATIVE IMPORTS
    # ========================================================

    def _uses_relative_imports(
        self,
        file: Path,
    ) -> bool:

        if not file.is_file():
            return False

        try:

            text = file.read_text(
                encoding="utf-8",
                errors="ignore",
            )

        except Exception:

            return False

        return bool(
            re.search(
                r"(?m)^\s*from\s+\.+",
                text,
            )
            or "__package__" in text
        )

    # ========================================================
    # CASE INSENSITIVE PATH
    # ========================================================

    def _find_case_insensitive(
        self,
        base: Path,
        parts: List[str],
    ) -> Optional[Path]:

        current = base

        for part in parts:

            if not current.is_dir():
                return None

            exact = current / part

            if exact.exists():

                current = exact
                continue

            wanted = part.lower()
            matches = []

            try:

                for child in current.iterdir():

                    if (
                        child.name.lower()
                        == wanted
                    ):

                        matches.append(
                            child
                        )

            except OSError:

                return None

            if len(matches) == 1:

                current = matches[0]

            else:

                return None

        return current

    # ========================================================
    # RESOLVE FILE
    # ========================================================

    def _resolve_requested_file(
        self,
        root: Path,
        requested: str,
    ) -> Optional[Path]:

        requested = requested.replace(
            "\\",
            "/",
        ).strip("/")

        parts = [
            p
            for p in requested.split("/")
            if p
        ]

        if not parts:
            return None

        exact = root.joinpath(
            *parts
        )

        if exact.is_file():
            return exact

        found = self._find_case_insensitive(
            root,
            parts,
        )

        if found and found.is_file():

            return found

        return None

    # ========================================================
    # MODULE NAME
    # ========================================================

    def _module_name_from_file(
        self,
        root: Path,
        file: Path,
    ) -> Optional[str]:

        try:

            relative = file.relative_to(
                root
            )

        except ValueError:

            return None

        if relative.suffix.lower() != ".py":
            return None

        parts = list(
            relative.with_suffix("").parts
        )

        if not parts:
            return None

        return ".".join(
            [
                root.name,
                *parts,
            ]
        )

    # ========================================================
    # PREPARE PACKAGE
    # ========================================================

    def _prepare_package_for_file(
        self,
        root: Path,
        file: Path,
    ) -> str:

        self._ensure_init_file(
            root
        )

        relative = file.relative_to(
            root
        )

        current = root

        for part in relative.parts[:-1]:

            current = current / part

            if current.is_dir():

                self._ensure_init_file(
                    current
                )

        module = (
            self._module_name_from_file(
                root,
                file,
            )
        )

        if not module:

            raise RuntimeError(
                f"Unable to create module "
                f"name for {file}"
            )

        return module

    # ========================================================
    # DISCOVER ENTRYPOINT
    # ========================================================

    def discover_entrypoint(
        self,
    ) -> Tuple[str, str]:

        root = self.get_root()

        requested = (
            self._normalise_run()
        )

        self.logger.info(
            "Requested run entry: %s",
            requested,
        )

        self.prepare_python_packages()

        # ----------------------------------------------------
        # 1. Exact file
        # ----------------------------------------------------

        exact = self._resolve_requested_file(
            root,
            requested,
        )

        if exact:

            if self._uses_relative_imports(
                exact
            ):

                module = (
                    self._prepare_package_for_file(
                        root,
                        exact,
                    )
                )

                return (
                    "module",
                    module,
                )

            return (
                "file",
                str(exact),
            )

        # ----------------------------------------------------
        # 2. Add .py
        # ----------------------------------------------------

        if not requested.lower().endswith(
            ".py"
        ):

            py_file = (
                self._resolve_requested_file(
                    root,
                    requested + ".py",
                )
            )

            if py_file:

                if self._uses_relative_imports(
                    py_file
                ):

                    module = (
                        self._prepare_package_for_file(
                            root,
                            py_file,
                        )
                    )

                    return (
                        "module",
                        module,
                    )

                return (
                    "file",
                    str(py_file),
                )

        # ----------------------------------------------------
        # 3. Explicit module
        # ----------------------------------------------------

        package_request = (
            requested.replace(
                "/",
                ".",
            )
        )

        if package_request.endswith(
            ".py"
        ):

            package_request = (
                package_request[:-3]
            )

        module_parts = (
            package_request.split(".")
        )

        if (
            module_parts
            and module_parts[0]
            == root.name
        ):

            module_parts = (
                module_parts[1:]
            )

        if module_parts:

            module_path = (
                root.joinpath(
                    *module_parts
                )
            )

            module_file = Path(
                str(module_path)
                + ".py"
            )

            if module_file.is_file():

                module = ".".join(
                    [
                        root.name,
                        *module_parts,
                    ]
                )

                return (
                    "module",
                    module,
                )

        # ----------------------------------------------------
        # 4. Root main.py
        # ----------------------------------------------------

        root_main = (
            root / "main.py"
        )

        if root_main.is_file():

            if self._uses_relative_imports(
                root_main
            ):

                module = (
                    self._prepare_package_for_file(
                        root,
                        root_main,
                    )
                )

                return (
                    "module",
                    module,
                )

            return (
                "file",
                str(root_main),
            )

        # ----------------------------------------------------
        # 5. Common entry files
        # ----------------------------------------------------

        for filename in (
            "app.py",
            "bot.py",
            "run.py",
            "start.py",
            "server.py",
        ):

            candidate = (
                self._resolve_requested_file(
                    root,
                    filename,
                )
            )

            if candidate:

                if self._uses_relative_imports(
                    candidate
                ):

                    module = (
                        self._prepare_package_for_file(
                            root,
                            candidate,
                        )
                    )

                    return (
                        "module",
                        module,
                    )

                return (
                    "file",
                    str(candidate),
                )

        # ----------------------------------------------------
        # 6. Recursive main.py
        # ----------------------------------------------------

        candidates = []

        for file in root.rglob(
            "main.py"
        ):

            relative = file.relative_to(
                root
            )

            if any(
                part in _IGNORED_DIRS
                for part in relative.parts
            ):

                continue

            module = (
                self._module_name_from_file(
                    root,
                    file,
                )
            )

            if module:

                candidates.append(
                    (
                        file,
                        module,
                    )
                )

        candidates.sort(
            key=lambda x: (
                len(
                    x[0].relative_to(
                        root
                    ).parts
                ),
                str(x[0]).lower(),
            )
        )

        if candidates:

            file, module = candidates[0]

            return (
                "module",
                module,
            )

        raise FileNotFoundError(
            "Could not determine bot "
            f"entry point. Requested={requested!r}, "
            f"root={root}"
        )

    # ========================================================
    # DOWNLOAD SOURCE
    # ========================================================

    def download_source(
        self,
    ) -> None:

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

                self.logger.info(
                    "Removing old bot directory: %s",
                    target,
                )

                shutil.rmtree(
                    target
                )

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

            src = Path(
                source
            )

            if not src.exists():

                raise FileNotFoundError(
                    f"Source not found: {source}"
                )

            if target.exists():

                shutil.rmtree(
                    target
                )

            shutil.copytree(
                src,
                target,
            )

        self.print_tree()

    # ========================================================
    # REQUIREMENTS
    # ========================================================

    def install_requirements(
        self,
    ) -> None:

        if not self.settings.get(
            "install_requirements",
            True,
        ):

            return

        root = self.get_root()

        requirements = (
            root / "requirements.txt"
        )

        if not requirements.is_file():

            self.logger.info(
                "No requirements.txt found "
                "for %s",
                self.config.name,
            )

            return

        self.logger.info(
            "Installing requirements for %s...",
            self.config.name,
        )

        command = [
            self.config.python,
            "-m",
            "pip",
            "install",
            "-r",
            str(requirements),
        ]

        subprocess.run(
            command,
            cwd=str(root),
            check=True,
        )

        self.logger.info(
            "Requirements installed for %s",
            self.config.name,
        )

    # ========================================================
    # ENVIRONMENT
    # ========================================================

    def build_environment(
        self,
        cwd: Path,
    ) -> Dict[str, str]:

        env = os.environ.copy()

        # Values in config.json override
        # existing environment variables.
        env.update(
            self.config.env
        )

        bots_dir = str(
            Path(
                self.settings[
                    "bots_dir"
                ]
            ).resolve()
        )

        bot_dir = str(
            cwd.resolve()
        )

        existing = env.get(
            "PYTHONPATH",
            "",
        )

        paths = []

        for path in (
            bot_dir,
            bots_dir,
            existing,
        ):

            if not path:
                continue

            for item in path.split(
                os.pathsep
            ):

                if (
                    item
                    and item not in paths
                ):

                    paths.append(
                        item
                    )

        env["PYTHONPATH"] = (
            os.pathsep.join(paths)
        )

        env.setdefault(
            "PYTHONUNBUFFERED",
            "1",
        )

        return env

    # ========================================================
    # START BOT
    # ========================================================

    def start(self) -> None:

        cwd = self.get_root()

        if not cwd.is_dir():

            raise FileNotFoundError(
                f"Bot directory not found: "
                f"{cwd}"
            )

        mode, entrypoint = (
            self.discover_entrypoint()
        )

        env = self.build_environment(
            cwd
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
            stdin=subprocess.DEVNULL,
        )

        self.logger.info(
            "Started %s (pid=%s)",
            self.config.name,
            self.process.pid,
        )

    # ========================================================
    # STOP BOT
    # ========================================================

    def stop(self) -> None:

        process = self.process

        if (
            process
            and process.poll() is None
        ):

            self.logger.info(
                "Stopping %s",
                self.config.name,
            )

            try:

                process.terminate()

                process.wait(
                    timeout=float(
                        self.settings[
                            "shutdown_timeout"
                        ]
                    )
                )

            except subprocess.TimeoutExpired:

                self.logger.warning(
                    "Force killing %s",
                    self.config.name,
                )

                process.kill()

                try:

                    process.wait(
                        timeout=5
                    )

                except Exception:
                    pass

            except Exception:

                self.logger.exception(
                    "Error stopping %s",
                    self.config.name,
                )

    # ========================================================
    # DIAGNOSTICS
    # ========================================================

    def diagnose_import_error(
        self,
    ) -> None:

        root = self.get_root()

        self.logger.error(
            "Bot %s failed.",
            self.config.name,
        )

        self.logger.error(
            "Bot root: %s",
            root,
        )

        if not root.exists():

            self.logger.error(
                "Bot root no longer exists."
            )

            return

        interesting = []

        try:

            for path in root.rglob("*"):

                if (
                    path.is_file()
                    and path.suffix.lower()
                    == ".py"
                ):

                    interesting.append(
                        str(
                            path.relative_to(
                                root
                            )
                        )
                    )

        except Exception:

            self.logger.exception(
                "Could not inspect bot files."
            )

            return

        interesting.sort()

        self.logger.error(
            "Python files currently available:"
        )

        for item in interesting[:200]:

            self.logger.error(
                "  %s",
                item,
            )


# ============================================================
# MULTIBOTS
# ============================================================

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
            self.settings[
                "log_level"
            ]
        )

        self.supervisors: List[
            BotSupervisor
        ] = []

        self.running = True

        self.lock = threading.Lock()

    # ========================================================
    # START SINGLE BOT
    # ========================================================

    def setup_bot(
        self,
        config: BotConfig,
    ) -> Optional[BotSupervisor]:

        if not config.enabled:

            self.logger.info(
                "Skipping disabled bot: %s",
                config.name,
            )

            return None

        supervisor = BotSupervisor(
            config,
            self.settings,
            self.logger,
        )

        try:

            self.logger.info(
                "=========================================="
            )

            self.logger.info(
                "Preparing bot: %s",
                config.name,
            )

            supervisor.download_source()

            supervisor.prepare_python_packages()

            supervisor.install_requirements()

            supervisor.start()

            self.logger.info(
                "Bot %s started successfully.",
                config.name,
            )

            return supervisor

        except Exception as exc:

            self.logger.error(
                "Failed to start %s: %s",
                config.name,
                exc,
            )

            self.logger.error(
                traceback.format_exc()
            )

            supervisor.diagnose_import_error()

            return None

    # ========================================================
    # RUN
    # ========================================================

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
                "No bots configured."
            )

        for config in configs:

            if not self.running:
                break

            supervisor = self.setup_bot(
                config
            )

            if supervisor:

                with self.lock:

                    self.supervisors.append(
                        supervisor
                    )

            time.sleep(
                float(
                    self.settings[
                        "start_delay"
                    ]
                )
            )

        self.logger.info(
            "MultiBots watchdog started."
        )

        # ====================================================
        # WATCHDOG
        # ====================================================

        while self.running:

            with self.lock:

                supervisors = list(
                    self.supervisors
                )

            for supervisor in supervisors:

                if not self.running:
                    break

                process = (
                    supervisor.process
                )

                if (
                    process is None
                    or process.poll() is None
                ):

                    continue

                return_code = (
                    process.returncode
                )

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

                if (
                    supervisor.restarts
                    < int(limit)
                ):

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

                    if not self.running:
                        break

                    try:

                        supervisor.start()

                    except Exception as exc:

                        self.logger.error(
                            "Failed to restart %s: %s",
                            supervisor.config.name,
                            exc,
                        )

                        self.logger.error(
                            traceback.format_exc()
                        )

                        supervisor.diagnose_import_error()

                else:

                    self.logger.error(
                        "Restart limit reached "
                        "for %s",
                        supervisor.config.name,
                    )

            time.sleep(
                float(
                    self.settings[
                        "watchdog_interval"
                    ]
                )
            )

    # ========================================================
    # SHUTDOWN
    # ========================================================

    def shutdown(self) -> None:

        if not self.running:
            return

        self.running = False

        self.logger.info(
            "Shutting down MultiBots..."
        )

        with self.lock:

            supervisors = list(
                self.supervisors
            )

        for supervisor in supervisors:

            supervisor.stop()

        self.logger.info(
            "MultiBots shutdown complete."
        )


# ============================================================
# BACKGROUND SUPERVISOR
# ============================================================

def run_multibots() -> None:

    global multibots_instance

    multibots_instance = MultiBots()

    try:

        multibots_instance.run()

    except Exception:

        multibots_instance.logger.exception(
            "Fatal MultiBots error"
        )

        multibots_instance.shutdown()


# ============================================================
# SIGNAL HANDLERS
# ============================================================

def handle_signal(
    signum,
    frame,
):

    global multibots_instance

    logging.getLogger(
        "multibots"
    ).info(
        "Received signal %s",
        signum,
    )

    if multibots_instance is not None:

        multibots_instance.shutdown()

    raise SystemExit(0)


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    global supervisor_thread

    logger = setup_logging(
        DEFAULTS["log_level"]
    )

    signal.signal(
        signal.SIGINT,
        handle_signal,
    )

    signal.signal(
        signal.SIGTERM,
        handle_signal,
    )

    # --------------------------------------------------------
    # Start MultiBots in background.
    # --------------------------------------------------------

    supervisor_thread = threading.Thread(
        target=run_multibots,
        name="multibots-supervisor",
        daemon=True,
    )

    supervisor_thread.start()

    # --------------------------------------------------------
    # Start HTTP server.
    #
    # Render detects this port and keeps the service alive.
    # --------------------------------------------------------

    host = DEFAULTS["host"]
    port = DEFAULTS["port"]

    logger.info(
        "================================================"
    )

    logger.info(
        "MultiBots %s starting...",
        __version__,
    )

    logger.info(
        "HTTP server: %s:%s",
        host,
        port,
    )

    logger.info(
        "Health endpoint: /health"
    )

    logger.info(
        "Status endpoint: /status"
    )

    logger.info(
        "================================================"
    )

    try:

        # IMPORTANT:
        # use_reloader=False prevents Flask from
        # starting the application twice.

        app.run(
            host=host,
            port=port,
            debug=False,
            threaded=True,
            use_reloader=False,
        )

    except KeyboardInterrupt:

        logger.info(
            "Keyboard interrupt received."
        )

    except Exception:

        logger.exception(
            "HTTP server failed."
        )

    finally:

        if multibots_instance is not None:

            multibots_instance.shutdown()


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()
