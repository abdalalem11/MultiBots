"""Unit tests for the configuration layer (ConfigLoader, BotConfig)."""
from __future__ import annotations

import json

import pytest

from main import ConfigError, ConfigLoader, BotConfig


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------
class TestBotNameValidation:
    def test_valid_names_accepted(self, settings, write_config, make_bot):
        make_bot("MyBot-1", "print('hi')")
        make_bot("bot_2", "print('hi')")
        write_config({
            "MyBot-1": {"source": "https://github.com/x/y.git", "run": "main.py"},
            "bot_2":   {"source": "https://github.com/x/z.git", "run": "main.py"},
        })
        bots, _ = ConfigLoader(settings).load()
        names = {b.name for b in bots}
        assert names == {"MyBot-1", "bot_2"}

    @pytest.mark.parametrize("bad_name", [
        "1starts_with_digit",      # leading digit
        "has space",               # whitespace
        "has/slash",               # path sep
        "has$dollar",              # special char
        "",                        # empty
        "x" * 100,                 # too long
    ])
    def test_invalid_names_rejected(self, settings, write_config, make_bot, bad_name):
        make_bot("valid_dummy", "print('hi')")  # need at least one bot dir
        write_config({
            "valid_dummy": {"source": "https://github.com/x/y.git", "run": "main.py"},
            bad_name:      {"source": "https://github.com/x/z.git", "run": "main.py"},
        })
        bots, _ = ConfigLoader(settings).load()
        # Invalid bot is skipped, valid one still loaded.
        assert {b.name for b in bots} == {"valid_dummy"}


class TestRequiredKeys:
    def test_missing_source_rejected(self, settings, write_config):
        write_config({"bot1": {"run": "main.py"}})
        bots, _ = ConfigLoader(settings).load()
        assert bots == []

    def test_missing_run_rejected(self, settings, write_config):
        write_config({"bot1": {"source": "https://github.com/x/y.git"}})
        bots, _ = ConfigLoader(settings).load()
        assert bots == []

    def test_empty_source_rejected(self, settings, write_config):
        write_config({"bot1": {"source": "", "run": "main.py"}})
        bots, _ = ConfigLoader(settings).load()
        assert bots == []

    def test_run_with_path_separator_rejected(self, settings, write_config):
        write_config({
            "bot1": {"source": "https://github.com/x/y.git", "run": "subdir/main.py"},
        })
        bots, _ = ConfigLoader(settings).load()
        assert bots == []

    def test_run_with_absolute_path_rejected(self, settings, write_config):
        write_config({
            "bot1": {"source": "https://github.com/x/y.git", "run": "/etc/passwd"},
        })
        bots, _ = ConfigLoader(settings).load()
        assert bots == []


class TestSourceValidation:
    @pytest.mark.parametrize("url", [
        "https://github.com/x/y.git",
        "http://example.com/x/y.git",
        "git@github.com:x/y.git",
        "ssh://git@github.com/x/y.git",
    ])
    def test_valid_git_urls(self, settings, write_config, url):
        write_config({"bot1": {"source": url, "run": "main.py"}})
        bots, _ = ConfigLoader(settings).load()
        assert len(bots) == 1
        assert bots[0].source == url

    @pytest.mark.parametrize("bad", [
        "ftp://example.com/x.git",     # wrong scheme
        "github.com/x/y.git",          # no scheme
        "file:///etc/passwd",          # local file
        "//github.com/x/y.git",        # protocol-relative
    ])
    def test_invalid_git_urls(self, settings, write_config, bad):
        write_config({"bot1": {"source": bad, "run": "main.py"}})
        bots, _ = ConfigLoader(settings).load()
        assert bots == []


class TestEnvValidation:
    def test_env_values_coerced_to_string(self, settings, write_config):
        write_config({
            "bot1": {
                "source": "https://github.com/x/y.git",
                "run": "main.py",
                "env": {"PORT": 8080, "DEBUG": True, "COUNT": 3.14},
            },
        })
        bots, _ = ConfigLoader(settings).load()
        assert bots[0].env == {"PORT": "8080", "DEBUG": "True", "COUNT": "3.14"}

    def test_env_with_empty_key_rejected(self, settings, write_config):
        write_config({
            "bot1": {
                "source": "https://github.com/x/y.git", "run": "main.py",
                "env": {"": "value"},
            },
        })
        bots, _ = ConfigLoader(settings).load()
        assert bots == []

    def test_env_not_dict_rejected(self, settings, write_config):
        write_config({
            "bot1": {
                "source": "https://github.com/x/y.git", "run": "main.py",
                "env": ["TOKEN", "foo"],
            },
        })
        bots, _ = ConfigLoader(settings).load()
        assert bots == []


# ---------------------------------------------------------------------------
# File-level errors
# ---------------------------------------------------------------------------
class TestConfigFileErrors:
    def test_missing_file_raises(self, settings):
        settings["config_path"] = "/nonexistent/path/config.json"
        with pytest.raises(ConfigError, match="not found"):
            ConfigLoader(settings).load()

    def test_invalid_json_raises(self, settings, write_config):
        # Write a file that isn't JSON
        path = settings["config_path"]
        with open(path, "w") as fh:
            fh.write("{ this is not json }")
        with pytest.raises(ConfigError, match="not valid JSON"):
            ConfigLoader(settings).load()

    def test_top_level_array_rejected(self, settings, write_config):
        # JSON arrays are not allowed — config must be an object.
        path = settings["config_path"]
        with open(path, "w") as fh:
            fh.write("[1, 2, 3]")
        with pytest.raises(ConfigError, match="must be an object"):
            ConfigLoader(settings).load()

    def test_empty_config_warns_but_returns_empty(self, settings, write_config):
        write_config({})
        bots, _ = ConfigLoader(settings).load()
        assert bots == []


# ---------------------------------------------------------------------------
# Optional fields + global inheritance
# ---------------------------------------------------------------------------
class TestOptionalFields:
    def test_defaults_applied_when_omitted(self, settings, write_config):
        write_config({
            "bot1": {"source": "https://github.com/x/y.git", "run": "main.py"},
        })
        bots, _ = ConfigLoader(settings).load()
        b = bots[0]
        assert b.enabled is True
        assert b.env == {}
        assert b.health_url == ""
        assert b.health_timeout == 5.0
        assert b.args == []
        assert b.timeout_graceful == 10.0

    def test_global_inheritance(self, settings, write_config):
        write_config(
            {"bot1": {"source": "https://github.com/x/y.git", "run": "main.py"}},
            global_cfg={"max_restarts": 99, "restart_delay_base": 7.5},
        )
        bots, _ = ConfigLoader(settings).load()
        assert bots[0].max_restarts == 99
        assert bots[0].restart_delay_base == 7.5

    def test_per_bot_overrides_global(self, settings, write_config):
        write_config({
            "bot1": {
                "source": "https://github.com/x/y.git", "run": "main.py",
                "max_restarts": 10,
            },
            "bot2": {"source": "https://github.com/x/z.git", "run": "main.py"},
        }, global_cfg={"max_restarts": 99})
        bots, _ = ConfigLoader(settings).load()
        by_name = {b.name: b for b in bots}
        assert by_name["bot1"].max_restarts == 10
        assert by_name["bot2"].max_restarts == 99

    def test_reserved_keys_skipped(self, settings, write_config):
        write_config({
            "_dashboard": {"password_hash": "x"},
            "_global": {"max_restarts": 5},
            "bot1": {"source": "https://github.com/x/y.git", "run": "main.py"},
        })
        bots, dash = ConfigLoader(settings).load()
        assert {b.name for b in bots} == {"bot1"}
        assert dash == {"password_hash": "x"}


# ---------------------------------------------------------------------------
# BotConfig helpers
# ---------------------------------------------------------------------------
class TestBotConfigHelpers:
    def test_resolve_cwd_default(self, settings):
        b = BotConfig(name="mybot", source="https://x.git", run="main.py")
        assert b.resolve_cwd(settings["bots_dir"]) == \
            f"{settings['bots_dir']}/mybot"

    def test_resolve_cwd_absolute_override(self, settings):
        b = BotConfig(name="mybot", source="https://x.git", run="main.py",
                      cwd="/custom/path")
        assert b.resolve_cwd(settings["bots_dir"]) == "/custom/path"

    def test_resolve_runfile(self, settings):
        b = BotConfig(name="mybot", source="https://x.git", run="bot.py")
        assert b.resolve_runfile(settings["bots_dir"]) == \
            f"{settings['bots_dir']}/mybot/bot.py"

    def test_to_public_dict_masks_env(self):
        b = BotConfig(
            name="mybot", source="https://x.git", run="main.py",
            env={"TOKEN": "sk-1234567890abcdef", "PUBLIC": "ok"},
        )
        d = b.to_public_dict()
        assert d["env_masked"]["TOKEN"].startswith("sk-1")
        assert "…" in d["env_masked"]["TOKEN"]
        assert d["env_masked"]["PUBLIC"] == "**"  # short value fully masked to same length
        assert d["env_keys"] == ["PUBLIC", "TOKEN"]
        assert d["has_env"] is True


# ---------------------------------------------------------------------------
# Backward compatibility — original config.json schema must still work
# ---------------------------------------------------------------------------
class TestBackwardCompatibility:
    def test_original_minimal_schema_loads(self, settings, write_config):
        """The exact schema from the original README's example."""
        write_config({
            "EbookBot": {
                "source": "https://github.com/user/Ebooks-Bot.git",
                "env": {"TOKEN": "abc123", "ID": "123", "HASH": "abc123"},
                "run": "main.py",
            },
            "PrivateBot": {
                "source": "https://user:token@github.com/user/private-bot.git",
                "env": {"TOKEN": "another-token"},
                "run": "bot.py",
            },
        })
        bots, _ = ConfigLoader(settings).load()
        assert len(bots) == 2
        by_name = {b.name: b for b in bots}
        assert by_name["EbookBot"].run == "main.py"
        assert by_name["PrivateBot"].env["TOKEN"] == "another-token"
