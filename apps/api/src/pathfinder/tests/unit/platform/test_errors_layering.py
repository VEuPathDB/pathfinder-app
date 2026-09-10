from __future__ import annotations

import importlib.util
from pathlib import Path


def _module_source(dotted: str) -> str:
    spec = importlib.util.find_spec(dotted)
    assert spec is not None
    assert spec.origin is not None
    return Path(spec.origin).read_text()


def test_platform_errors_has_no_fastapi_dependency() -> None:
    """Pure error types must not pull FastAPI (keeps the domain layer pure)."""
    source = _module_source("pathfinder.platform.errors")
    assert "fastapi" not in source


def test_error_handlers_module_owns_fastapi_handlers() -> None:
    source = _module_source("pathfinder.platform.error_handlers")
    assert "async def veupathdb_error_handler" in source
    assert "async def http_exception_handler" in source
    assert "async def request_validation_handler" in source
    assert "async def rate_limit_handler" in source
