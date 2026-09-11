"""The generated spec is the production contract, whatever the process env."""

from pathlib import Path

import pytest

from pathfinder.devtools.openapi import (
    DevRouteInSpecError,
    _dev_only_paths,
    _refuse_dev_routes,
    _spec_with_stable_overrides,
    _SpecPaths,
    generate_openapi_json,
)
from pathfinder.main import create_app
from pathfinder.platform.config import get_settings

DEV_LOGIN = "/api/v1/dev/login"


def test_the_spec_never_carries_dev_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "pathfinder_chat_provider", "mock")

    spec = _spec_with_stable_overrides()

    paths = _SpecPaths.model_validate(spec).paths
    dev_paths = [p for p in paths if p.startswith("/api/v1/dev/")]
    assert dev_paths == []


def test_the_dev_paths_are_read_from_the_dev_router() -> None:
    assert DEV_LOGIN in _dev_only_paths()


def test_a_spec_naming_a_dev_route_is_refused_by_name() -> None:
    with pytest.raises(DevRouteInSpecError) as raised:
        _refuse_dev_routes({"paths": {DEV_LOGIN: {}, "/api/v1/conversations": {}}})

    assert DEV_LOGIN in str(raised.value)
    assert "/api/v1/conversations" not in str(raised.value)


def test_nothing_is_written_when_the_app_mounts_a_dev_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "pathfinder.devtools.openapi.create_app",
        lambda *, include_dev_routes=None: create_app(include_dev_routes=True),
    )
    out_path = tmp_path / "openapi.json"

    with pytest.raises(DevRouteInSpecError):
        generate_openapi_json(out_path=out_path)

    assert not out_path.exists()
