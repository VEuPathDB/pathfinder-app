"""The label each emitted reply's notes take, so no two replies share a footnote id."""

from __future__ import annotations

from uuid import uuid4


def note_label() -> str:
    return f"n{uuid4().hex[:8]}-"


__all__ = ["note_label"]
