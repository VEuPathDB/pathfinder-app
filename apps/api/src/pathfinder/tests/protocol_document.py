"""Read PROTOCOL.md, which ships beside the packages that speak it."""

from __future__ import annotations

import re
from pathlib import Path

import assistant_core

PROTOCOL = Path(assistant_core.__file__).parents[4] / "PROTOCOL.md"

_SECTION = re.compile(r"<!-- (\w+):begin -->\n(.*?)\n<!-- \1:end -->", re.DOTALL)


def protocol_section(name: str) -> str:
    """Return the body of one delimited block, or fail naming the block."""
    for found in _SECTION.finditer(PROTOCOL.read_text()):
        if found.group(1) == name:
            return found.group(2)
    msg = f"PROTOCOL.md has no <!-- {name}:begin --> section"
    raise AssertionError(msg)
