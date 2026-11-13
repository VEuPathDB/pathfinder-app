"""The client reads the host's settings, and never computes a config path."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from veupathdb import VEuPathDBSettings, get_veupathdb_settings

from strategist.platform.config import Settings, get_settings


def test_the_host_instance_serves_the_client() -> None:
    assert get_veupathdb_settings() is get_settings()


def test_the_application_settings_extend_the_client_settings() -> None:
    assert issubclass(Settings, VEuPathDBSettings)


def test_the_client_settings_keep_the_environment_variable_names() -> None:
    assert set(VEuPathDBSettings.model_fields) == {
        "veupathdb_sites_config",
        "veupathdb_oauth_url",
        "veupathdb_internal_strategy_name_prefix",
        "veupathdb_former_internal_strategy_name_prefixes",
        "veupathdb_user_agent",
        "veupathdb_concurrent_searches_per_site",
    }


def test_this_application_writes_its_own_prefix() -> None:
    assert (
        Settings().veupathdb_internal_strategy_name_prefix == "__strategist_internal__:"
    )


def test_this_application_still_reads_what_it_wrote_before() -> None:
    assert Settings().veupathdb_former_internal_strategy_name_prefixes == (
        "__pathfinder_internal__:Pathfinder ",
        "__pathfinder_internal__:Strategist ",
        "__pathfinder_internal__:",
    )


def test_the_client_settings_module_computes_no_path() -> None:
    spec = importlib.util.find_spec("veupathdb.settings")
    assert spec is not None
    assert spec.origin is not None
    source = Path(spec.origin).read_text()

    assert "__file__" not in source
    assert "config.toml" not in source
