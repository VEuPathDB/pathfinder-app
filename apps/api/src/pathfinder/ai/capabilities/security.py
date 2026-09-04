from __future__ import annotations

import asyncio
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from assistant_core.platform.logging import get_logger

from pathfinder.ai.capabilities.piguard import (
    InvisibleTextScanner,
    PIGuardScanner,
    SecurityRejectionError,
    resolve_model_dir,
)
from pathfinder.platform.config import get_settings

logger = get_logger(__name__)


_PURE_APPROVAL_BYPASS = re.compile(
    r"""^\s*(?:
        yes|yep|yeah|ok|okay|sure|fine|
        approved?|proceed|go(?:\s+ahead)?|continue|
        run\s+it|execute(?:\s+(?:it|the\s+plan))?|launch(?:\s+it)?|
        do\s+it|confirm(?:ed)?|accept(?:ed)?|
        sounds?\s+good|looks?\s+good|
        perfect|great
    )[\s\.\!\,]*$""",
    re.IGNORECASE | re.VERBOSE,
)

_APPROVAL_CONNECTIVE_RE = re.compile(
    r"^\s*(?P<head>[^,.\!\?]{0,40}?)\s*[,\.]\s*(?P<tail>[^,.\!\?]{0,40})[\s\.\!\?]*$",
)

_MAX_APPROVAL_LENGTH = 80


def is_pure_approval(text: str) -> bool:
    """Strict whitelist: the text is nothing more than an approval phrase.

    One or two approval words joined by a connective, within
    ``_MAX_APPROVAL_LENGTH`` characters. Everything else is not an approval.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > _MAX_APPROVAL_LENGTH:
        return False
    if _PURE_APPROVAL_BYPASS.match(stripped):
        return True
    match = _APPROVAL_CONNECTIVE_RE.match(stripped)
    if match is None:
        return False
    head = match.group("head") or ""
    tail = match.group("tail") or ""
    return bool(
        _PURE_APPROVAL_BYPASS.match(head) and _PURE_APPROVAL_BYPASS.match(tail),
    )


@dataclass
class UserInputScanner:
    """Single-scan-per-turn trust boundary for user input.

    The scanners are built under a lock, so one caller pays the onnxruntime
    and tokenizer load. ``ensure_loaded`` moves that cost to startup.
    """

    injection_threshold: float = 0.90
    model_dir: Path = field(default_factory=resolve_model_dir)
    _piguard: PIGuardScanner | None = field(default=None, init=False, repr=False)
    _invisible: InvisibleTextScanner | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _lock: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )

    def ensure_loaded(self) -> tuple[PIGuardScanner, InvisibleTextScanner]:
        if self._piguard is not None and self._invisible is not None:
            return self._piguard, self._invisible
        with self._lock:
            if self._piguard is None:
                self._piguard = PIGuardScanner(
                    model_dir=self.model_dir,
                    threshold=self.injection_threshold,
                )
            if self._invisible is None:
                self._invisible = InvisibleTextScanner()
            return self._piguard, self._invisible

    def scan(self, text: str) -> None:
        """Scan one user message. Raise ``SecurityRejectionError`` if rejected.

        Text that matches the pure-approval whitelist skips PIGuard: short
        affirmatives score above the injection threshold although they carry
        no instruction.
        """
        if is_pure_approval(text):
            return
        piguard, invisible = self.ensure_loaded()
        piguard_name = "PIGuardScanner"
        invisible_name = "InvisibleTextScanner"
        _, valid, score = piguard.scan(text)
        if not valid:
            logger.warning(
                "Input rejected by security scanner",
                scanner=piguard_name,
                risk_score=score,
            )
            raise SecurityRejectionError(piguard_name, score)
        _, visible_valid, visible_score = invisible.scan(text)
        if not visible_valid:
            logger.warning(
                "Input rejected by security scanner",
                scanner=invisible_name,
                risk_score=visible_score,
            )
            raise SecurityRejectionError(invisible_name, visible_score)


_scanner = UserInputScanner()


def warm_up_scanner() -> None:
    """Build the scanners the request path calls, so no request pays the load."""
    _scanner.ensure_loaded()


async def scan_user_input(text: str) -> None:
    """Offload the CPU-bound scan to a thread so the event loop stays free."""
    if not get_settings().piguard_enabled:
        return
    await asyncio.to_thread(_scanner.scan, text)


__all__ = [
    "SecurityRejectionError",
    "UserInputScanner",
    "is_pure_approval",
    "scan_user_input",
    "warm_up_scanner",
]
