import re

_AN_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")


def as_read(text: str) -> str:
    return _AN_ESCAPE.sub(r"\1", text)


__all__ = ["as_read"]
