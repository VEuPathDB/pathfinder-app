"""First-pass redaction: the patterns that are never science.

An email address and a URL credential identify a person and never describe a
strategy, so both are removed before anything is staged. No rule reads digits:
in this domain a digit run is a gene count, a threshold or a WDK id, and a
false positive would silently corrupt the case. The full redaction is the
human curation step that promotes a case.
"""

from __future__ import annotations

import re

EMAIL_PLACEHOLDER = "[redacted-email]"
CREDENTIAL_PLACEHOLDER = "[redacted-credential]"

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# The placeholder is not a credential, so redacted text passes the check.
_URL_CREDENTIAL = re.compile(
    rf"(?<=://)(?!{re.escape(CREDENTIAL_PLACEHOLDER)}@)[^/\s@]+(?=@)"
)


class RedactionFailedError(ValueError):
    """Raised when redacted text still carries a pattern that must never ship.

    It is a ``ValueError`` so a model validator turns it into a validation
    error, and an extract that carries an identity pattern cannot be built.
    """


def redact_text(text: str) -> str:
    """Replace the identity patterns in *text* with their placeholders."""
    without_credentials = _URL_CREDENTIAL.sub(CREDENTIAL_PLACEHOLDER, text)
    return _EMAIL.sub(EMAIL_PLACEHOLDER, without_credentials)


def assert_redacted(text: str) -> bool:
    """True when *text* carries no identity pattern, or a failure naming the one it does."""
    if _URL_CREDENTIAL.search(text):
        msg = "text still carries a URL credential"
        raise RedactionFailedError(msg)
    if _EMAIL.search(text):
        msg = "text still carries an email address"
        raise RedactionFailedError(msg)
    return True


__all__ = ["RedactionFailedError", "assert_redacted", "redact_text"]
