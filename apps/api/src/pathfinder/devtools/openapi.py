"""Developer tooling for keeping OpenAPI spec in sync.

This is intentionally NOT run by the API at runtime. It writes repo files.
"""

import argparse
import json
from pathlib import Path

import yaml
from assistant_core.platform.types import JSONObject
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from pathfinder.main import create_app
from pathfinder.transport.http.routers import dev, dev_site_login


class DevRouteInSpecError(RuntimeError):
    """The spec names a route only the mock overlay or local development mounts."""

    def __init__(self, paths: list[str]) -> None:
        self.paths = paths
        message = (
            f"The spec names dev-only route(s) {paths}. The published spec is the "
            f"production contract, so nothing was written. Generate it from the "
            f"application, not from whichever container is running."
        )
        super().__init__(message)


class _SpecPaths(BaseModel):
    """The path map of an OpenAPI document."""

    model_config = ConfigDict(extra="ignore")

    paths: dict[str, JsonValue] = Field(default_factory=dict)


def _dev_only_paths() -> frozenset[str]:
    """The paths the dev routers mount, read from the routers themselves."""
    return frozenset(
        route.path
        for router in (dev.router, dev_site_login.router)
        for route in router.routes
        if isinstance(route, APIRoute)
    )


def _refuse_dev_routes(spec: JSONObject) -> None:
    named = sorted(set(_SpecPaths.model_validate(spec).paths) & _dev_only_paths())
    if named:
        raise DevRouteInSpecError(named)


def _repo_root() -> Path:
    # .../apps/api/src/pathfinder/devtools/openapi.py -> repo root
    return Path(__file__).resolve().parents[5]


def _spec_with_stable_overrides() -> JSONObject:
    # The published spec is the production contract; dev routes never enter it.
    app = create_app(include_dev_routes=False)
    spec = app.openapi()
    _refuse_dev_routes(spec)

    # Keep a stable OAS version string if FastAPI omits/changes it.
    spec.setdefault("openapi", "3.1.0")

    # Preserve/define servers (helps local dev).
    spec.setdefault(
        "servers",
        [
            {"url": "http://localhost:8000", "description": "Local development"},
        ],
    )
    return spec


def generate_openapi_yaml(*, out_path: Path | None = None) -> Path:
    root = _repo_root()
    path = out_path or (root / "packages" / "spec" / "openapi.yaml")
    path.parent.mkdir(parents=True, exist_ok=True)

    spec = _spec_with_stable_overrides()
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            spec,
            f,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )
    return path


def generate_openapi_json(*, out_path: Path | None = None) -> Path:
    root = _repo_root()
    path = out_path or (root / "packages" / "spec" / "openapi.json")
    path.parent.mkdir(parents=True, exist_ok=True)

    spec = _spec_with_stable_overrides()
    path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return path


def check_openapi_yaml(*, openapi_path: Path | None = None) -> bool:
    root = _repo_root()
    path = openapi_path or (root / "packages" / "spec" / "openapi.yaml")
    if not path.exists():
        msg = f"Missing {path}. Run generate first."
        raise FileNotFoundError(msg)

    actual = _spec_with_stable_overrides()
    expected_text: str = yaml.safe_dump(
        actual,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )
    current_text = path.read_text("utf-8")
    return current_text == expected_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser(
        "generate",
        help="Write packages/spec/openapi.yaml and openapi.json from the FastAPI app",
    )
    sub.add_parser(
        "check", help="Exit non-zero if packages/spec/openapi.yaml is out of date"
    )
    args = parser.parse_args(argv)

    if args.cmd == "generate":
        generate_openapi_yaml()
        generate_openapi_json()
        return 0

    ok = check_openapi_yaml()
    if not ok:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
