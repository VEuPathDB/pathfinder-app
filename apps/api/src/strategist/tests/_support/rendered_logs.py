from __future__ import annotations

import io
import logging
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stdout

from assistant_core.platform.logging import setup_logging
from pydantic import JsonValue, TypeAdapter

_LINE = TypeAdapter(dict[str, JsonValue])


class RenderedLogs:
    def __init__(self, sink: io.StringIO) -> None:
        self._sink = sink

    def lines(self) -> list[dict[str, JsonValue]]:
        return [
            _LINE.validate_json(text) for text in self._sink.getvalue().splitlines()
        ]

    def line(self, event: str) -> dict[str, JsonValue]:
        (found,) = [line for line in self.lines() if line["event"] == event]
        return found


@contextmanager
def rendered_logs() -> Iterator[RenderedLogs]:
    root = logging.getLogger()
    kept, level = list(root.handlers), root.level
    sink = io.StringIO()
    with redirect_stdout(sink):
        setup_logging()
    try:
        yield RenderedLogs(sink)
    finally:
        root.handlers = kept
        root.setLevel(level)
