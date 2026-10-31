from __future__ import annotations

import html
import re
from collections.abc import Callable

_DEST = r"(?:[^()\s]|\([^()\s]*\))*"
_INLINE = re.compile(rf"!?\[(?P<text>[^\[\]]*)\]\(\s*(?P<dest>{_DEST})(?:\s+[^()]*)?\)")
_HTML = re.compile(
    r"<[^<>]*\b(?:href|src)\s*=\s*['\"]?(?P<dest>[^'\"\s>]*)[^<>]*>", re.IGNORECASE
)
_AUTOLINK = re.compile(r"<(?P<dest>[A-Za-z][\w+.-]*:[^<>\s]*)>")
_BARE = re.compile(
    r"(?<![\w/\\])(?P<dest>(?:[A-Za-z][\w+.-]*://|www\.|"
    r"[A-Za-z][\w+.-]*:[\\/]+|"
    r"(?:mailto|javascript|vbscript|data|file|tel|doi):|[\\/]{2}(?=[\w-]+\.))"
    r"[^\s<>()\[\]\"'`]*(?:\([^\s()]*\))?)",
    re.IGNORECASE,
)
_TRAILING = ".,;:!?"
_A_MARK = re.compile(r"[!-/:-@\[-`{-~]")


def _bare(match: re.Match[str]) -> tuple[str, str]:
    dest = match.group("dest").rstrip(_TRAILING)
    return dest, match.group()[len(dest) :]


_PATTERNS: tuple[
    tuple[re.Pattern[str], Callable[[re.Match[str]], tuple[str, str]]], ...
] = (
    (_INLINE, lambda m: (m.group("dest"), m.group("text"))),
    (_HTML, lambda m: (m.group("dest"), "")),
    (_AUTOLINK, lambda m: (m.group("dest"), "")),
    (_BARE, _bare),
)


def _unlinked(text: str) -> tuple[str, list[str]]:
    found: list[str] = []
    plain = html.unescape(text)
    for pattern, read in _PATTERNS:

        def kept(
            match: re.Match[str], read: Callable[..., tuple[str, str]] = read
        ) -> str:
            dest, shown = read(match)
            found.append(dest)
            return shown

        plain = pattern.sub(kept, plain)
    return plain, found


def plain_markdown(text: str) -> str:
    return _A_MARK.sub(r"\\\g<0>", html.unescape(text))


def written_links(text: str) -> list[str]:
    return _unlinked(text)[1]


__all__ = ["plain_markdown", "written_links"]
