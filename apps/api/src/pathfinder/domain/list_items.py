"""The item numbers of a reply's ordered lists, which are marks and not facts."""

from __future__ import annotations

import re

_AN_ITEM_NUMBER = re.compile(r"^\s*(\d+)[.)](?=\s)", re.MULTILINE)


def without_item_numbers(text: str) -> str:
    """The text with each ordered list's item numbers taken out. An item number
    is one that starts a list or follows the item number before it."""
    previous = 0

    def exempt(match: re.Match[str]) -> str:
        nonlocal previous
        number = int(match.group(1))
        if number not in (1, previous + 1):
            return match.group()
        previous = number
        return " "

    return _AN_ITEM_NUMBER.sub(exempt, text)


__all__ = ["without_item_numbers"]
