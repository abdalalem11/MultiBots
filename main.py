"""
MultiBots - Multi-bot supervisor
--------------------------------
Downloads bot sources from config.json automatically,
prepares Python package structures, discovers the correct
entry point, installs requirements, starts and supervises
each bot.

Version: 3.0.1
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
import traceback
import threading

from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


__version__ = "3.0.1"


# ============================================================
# DEFAULT SETTINGS
# ============================================================

DEFAULTS: Dict[str, Any] = {
    # Render provides PORT automatically.
    "port": int(
        os.environ.get(
            "PORT",
            os.environ.get("MB_PORT", "10000"),
        )
    ),

    "host": os.environ.get(
        "HOST",
        os.environ.get("MB_HOST", "0.0.0.0"),
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
# HEALTH SERVER FOR RENDER
# ============================================================

def start_health_server(
    host: str,
    port: int,
    logger: logging.Logger,
) -> Optional[ThreadingHTTPServer]:

    class HealthHandler(BaseHTTPRequestHandler):

        def do_GET(self):

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8",
            )

            self.end_headers()

            self.wfile.write(
                b"MultiBots is running"
            )

        def do_HEAD(self):

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8",
            )

            self.end_headers()

        def log_message(
            self,
            format,
            *args,
        ):
            return

    try:

        server = ThreadingHTTPServer(
            (host, port),
            HealthHandler,
        )

        thread = threading.Thread(
            target=server.serve_forever,
            daemon=True,
        )

        thread.start()

        logger.info(
            "Health server listening on %s:%s",
            host,
            port,
        )

        return server

    except Exception:

        logger.exception(
            "Failed to start health server on %s:%s",
            host,
            port,
        )

        return None


# ============================================================
# CONFIG
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

            raw_env = item.get(
                "env",
                {},
            )

            if not isinstance(
                raw_env,
                dict,
            ):

                raise ConfigError(
                    f"Bot {name}: env must be an object"
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
                    f"Bot {name}: args must be a list"
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

        try:

            init_file.write_text(
                "",
                encoding="utf-8",
            )

            self.logger.info(
                "Created missing package file: %s",
                init_file,
            )

        except Exception:

            self.logger.exception(
                "Could not create package file: %s",
                init_file,
            )

            raise

    # ========================================================
    # PREPARE ALL PACKAGES
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
    # RELATIVE IMPORT DETECTION
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

        relative_import = re.search(
            r"(?m)^\s*from\s+\.+",
            text,
        )

        package_usage = (
            "__package__"
            in text
        )

        return bool(
            relative_import
            or package_usage
        )

    # ========================================================
    # FIND CASE-INSENSITIVE PATH
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

            exact = (
                current / part
            )

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

            elif len(matches) > 1:

                self.logger.warning(
                    "Multiple case-insensitive "
                    "matches for %s under %s",
                    part,
                    current,
                )

                return None

            else:

                return None

        return current

    # ========================================================
    # RESOLVE REQUESTED FILE
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

            if str(found) != str(exact):

                self.logger.warning(
                    "Case-insensitive path match: "
                    "%s -> %s",
                    requested,
                    found,
                )

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
    # PREPARE MODULE PACKAGE
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

            current = (
                current / part
            )

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
                f"Unable to create module name "
                f"for {file}"
            )

        return module

    # ========================================================
    # DISCOVER ENTRY POINT
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

        # 1. Exact requested file
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

                self.logger.info(
                    "Relative imports detected."
                )

                self.logger.info(
                    "Entry point selected: module -> %s",
                    module,
                )

                return (
                    "module",
                    module,
                )

            self.logger.info(
                "Entry point selected: file -> %s",
                exact,
            )

            return (
                "file",
                str(exact),
            )

        # 2. Add .py
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

                    self.logger.info(
                        "Relative imports detected."
                    )

                    self.logger.info(
                        "Entry point selected: "
                        "module -> %s",
                        module,
                    )

                    return (
                        "module",
                        module,
                    )

                return (
                    "file",
                    str(py_file),
                )

        # 3. Explicit module
        package_request = (
            requested
            .replace("/", ".")
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

                self.logger.info(
                    "Entry point selected: "
                    "module -> %s",
                    module,
                )

                return (
                    "module",
                    module,
                )

        # 4. Root main.py
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

                self.logger.info(
                    "Root main.py uses relative imports."
                )

                self.logger.info(
                    "Automatically selected module: %s",
                    module,
                )

                return (
                    "module",
                    module,
                )

            self.logger.info(
                "Automatically selected root main.py: %s",
                root_main,
            )

            return (
                "file",
                str(root_main),
            )

        # 5. Common files
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

        # 6. Search main.py recursively
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
                    x[0]
                    .relative_to(root)
                    .parts
                ),
                str(x[0]).lower(),
            )
        )

        if candidates:

            file, module = (
                candidates[0]
            )

            self.logger.info(
                "Automatically selected "
                "package entry: %s",
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

    # ========================================================
    # SOURCE DOWNLOAD
    # ========================================================

    def download_source(
        self,
    ) -> None:

        target = self.get_root()

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        source = (
            self.config.source
        )

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

            self.logger.info(
                "Requirement installation disabled."
            )

            return

        root = self.get_root()

        requirements = (
            root / "requirements.txt"
        )

        if not requirements.is_file():

            self.logger.info(
                "No requirements.txt found for %s",
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

        self.logger.info(
            "Requirements command: %s",
            " ".join(
                repr(str(x))
                for x in command
            ),
        )

       
