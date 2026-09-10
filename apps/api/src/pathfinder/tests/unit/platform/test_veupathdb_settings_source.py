"""The client reads the host's settings, and never computes a config path."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from veupathdb.settings import VEuPathDBSettings, get_veupathdb_settings

from pathfinder.platform.config import Settings, get_settings


def test_the_host_instance_serves_the_client() -> None:
    assert get_veupathdb_settings() is get_settings()


def test_the_application_settings_extend_the_client_settings() -> None:
    assert issubclass(Settings, VEuPathDBSettings)


def test_the_client_settings_keep_the_environment_variable_names() -> None:
    assert set(VEuPathDBSettings.model_fields) == {
        "veupathdb_sites_config",
        "veupathdb_auth_token",
        "veupathdb_oauth_url",
        "veupathdb_internal_strategy_name_prefix",
    }


def test_this_application_keeps_the_prefix_it_has_always_written() -> None:
    """A helper strategy already in an account carries this prefix."""
    assert (
        Settings().veupathdb_internal_strategy_name_prefix == "__pathfinder_internal__:"
    )


def test_the_client_settings_module_computes_no_path() -> None:
    spec = importlib.util.find_spec("veupathdb.settings")
    assert spec is not None
    assert spec.origin is not None
    source = Path(spec.origin).read_text()

    assert "__file__" not in source
    assert "config.toml" not in source
