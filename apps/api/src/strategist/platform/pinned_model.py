"""The one model a debugger or eval run pins for every role; outside such a run no model is pinned."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_pinned: ContextVar[str | None] = ContextVar("pinned_model", default=None)


def pinned_model() -> str | None:
    return _pinned.get()


@contextmanager
def pin_model(model_id: str) -> Iterator[None]:
    token = _pinned.set(model_id)
    try:
        yield
    finally:
        _pinned.reset(token)


__all__ = ["pin_model", "pinned_model"]
