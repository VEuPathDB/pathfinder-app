from __future__ import annotations

import re

_A_TOKEN = re.compile(r"[\w:./,%+-]+")
_EDGE_MARKS = ".,:;/+-_"
_NUMBER = r"\d[\d,]*(?:\.\d+)?"
_A_NUMBER = re.compile(rf"[+-]?{_NUMBER}(?:[-/]{_NUMBER})*%?")
_AN_ITEM_NUMBER = re.compile(r"^\s*(\d+)[.)](?=\s)", re.MULTILINE)
_A_RECORD = re.compile(r"\[record:[^\[\]\s]+\]")


def _without_item_numbers(text: str) -> str:
    previous = 0

    def exempt(match: re.Match[str]) -> str:
        nonlocal previous
        number = int(match.group(1))
        if number not in (1, previous + 1):
            return match.group()
        previous = number
        return " "

    return _AN_ITEM_NUMBER.sub(exempt, text)


def written_numbers(text: str) -> list[str]:
    plain = _without_item_numbers(_A_RECORD.sub(" ", text))
    tokens = (found.strip(_EDGE_MARKS) for found in _A_TOKEN.findall(plain))
    return list(dict.fromkeys(t for t in tokens if _A_NUMBER.fullmatch(t)))


__all__ = ["written_numbers"]
