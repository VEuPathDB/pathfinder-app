"""The precision a number value shows: the decimals of the parameter's
published initial value, never more than four significant digits."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

_A_DECIMAL = re.compile(r"[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
_SIGNIFICANT = 4


def shown_decimals(initial: str | None) -> int | None:
    """The decimal places a published number shows, or None for no number."""
    text = (initial or "").strip()
    if _A_DECIMAL.fullmatch(text) is None:
        return None
    mantissa, _, exponent = text.casefold().partition("e")
    return max(0, len(mantissa.partition(".")[2]) - int(exponent or 0))


def _at(number: Decimal, places: int) -> Decimal:
    return number.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def rounded_number(text: str, decimals: int | None) -> str | None:
    """The number at ``decimals`` places, capped at four significant digits,
    and at four significant digits when ``decimals`` shows zero. None when the
    text is no number. An integer is unchanged."""
    if _A_DECIMAL.fullmatch(text) is None:
        return None
    number = Decimal(text)
    if number == number.to_integral_value():
        return text
    significant = max(0, _SIGNIFICANT - 1 - number.adjusted())
    shown = _at(number, significant if decimals is None else min(decimals, significant))
    if shown == 0:
        shown = _at(number, significant)
    written = f"{shown:f}"
    return written.rstrip("0").rstrip(".") if "." in written else written


__all__ = ["rounded_number", "shown_decimals"]
