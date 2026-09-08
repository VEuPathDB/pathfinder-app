"""The dev-login credential exists only under the mock overlay.

A dev-login session skips the VEuPathDB identity match, so production must be
unable to mint one.
"""

from __future__ import annotations

from pathlib import Path

import pathfinder
from pathfinder.main import create_app
from pathfinder.tests._support.routes import api_routes
from pathfinder.transport.http.routers import dev

_MINTER = "create_dev_login_token"
_ALLOWED_MINTERS = {
    Path("platform/security.py"),
    Path("transport/http/routers/dev.py"),
}


def _endpoints(*, include_dev_routes: bool) -> set[object]:
    app = create_app(include_dev_routes=include_dev_routes)
    return {route.endpoint for route in api_routes(app.routes)}


def test_the_production_app_has_no_dev_login_route() -> None:
    assert dev.dev_login not in _endpoints(include_dev_routes=False)


def test_the_overlay_app_does_have_it() -> None:
    assert dev.dev_login in _endpoints(include_dev_routes=True)


def test_only_the_dev_router_mints_a_dev_login_token() -> None:
    root = Path(pathfinder.__file__).parent
    minters = {
        source.relative_to(root)
        for source in root.rglob("*.py")
        if not source.is_relative_to(root / "tests") and _MINTER in source.read_text()
    }

    assert minters == _ALLOWED_MINTERS
