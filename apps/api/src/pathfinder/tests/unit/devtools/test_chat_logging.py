"""The debugger's log chain flattens a traceback before the renderer reads it."""

from collections.abc import Iterator

import pytest
import structlog

from pathfinder.devtools.chat import route_framework_logs_to_stderr


@pytest.fixture
def restored_structlog() -> Iterator[None]:
    saved = structlog.get_config()
    yield
    structlog.configure(**saved)


def test_the_debugger_formats_exc_info_before_the_renderer(
    restored_structlog: None,
) -> None:
    del restored_structlog
    route_framework_logs_to_stderr()
    processors = structlog.get_config()["processors"]
    assert structlog.processors.format_exc_info in processors
    renderer = processors[-1]
    assert isinstance(renderer, structlog.dev.ConsoleRenderer)
    assert processors.index(structlog.processors.format_exc_info) < len(processors) - 1
