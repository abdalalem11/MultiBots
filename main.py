# ---------------------------------------------------------------------------
# Repository manager — clone/update bot sources from config.json
# ---------------------------------------------------------------------------

def _prepare_bot_source(cfg: BotConfig, bots_dir: str, log: logging.Logger) -> bool:
    """
    Clone the bot repository from cfg.source into:
        <bots_dir>/<bot_name>

    If the directory already contains a git repository, update it with
    git pull instead of cloning again.
    """
    target_dir = Path(cfg.resolve_cwd(bots_dir))
    git_dir = target_dir / ".git"

    try:
        # Existing repository -> update it
        if git_dir.is_dir():
            log.info(
                "Updating source for bot '%s' from %s",
                cfg.name,
                cfg.source,
            )

            result = subprocess.run(
                ["git", "-C", str(target_dir), "pull", "--ff-only"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=180,
            )

            if result.returncode != 0:
                log.error(
                    "Failed to update bot '%s': %s",
                    cfg.name,
                    result.stdout.strip(),
                )
                return False

            log.info(
                "Source for bot '%s' updated successfully.",
                cfg.name,
            )
            return True

        # Directory exists but isn't a git repository
        if target_dir.exists() and any(target_dir.iterdir()):
            log.warning(
                "Bot directory '%s' exists but is not a git repository. "
                "Removing it before clone.",
                target_dir,
            )

            import shutil
            shutil.rmtree(target_dir)

        target_dir.parent.mkdir(parents=True, exist_ok=True)

        log.info(
            "Cloning bot '%s' from %s -> %s",
            cfg.name,
            cfg.source,
            target_dir,
        )

        result = subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                cfg.source,
                str(target_dir),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            log.error(
                "Failed to clone bot '%s': %s",
                cfg.name,
                result.stdout.strip(),
            )
            return False

        log.info(
            "Bot '%s' source downloaded successfully.",
            cfg.name,
        )
        return True

    except FileNotFoundError:
        log.error(
            "git command was not found. Make sure git is installed "
            "in the Render environment."
        )
        return False

    except subprocess.TimeoutExpired:
        log.error(
            "Timeout while downloading/updating bot '%s'.",
            cfg.name,
        )
        return False

    except Exception as exc:
        log.exception(
            "Unexpected error preparing bot '%s': %s",
            cfg.name,
            exc,
        )
        return False
