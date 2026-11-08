"""Which sites offer the gene-model audit."""

from __future__ import annotations

from typing import Final
from urllib.parse import urlsplit

AUDIT_HOST_PREFIX: Final = "muharram."


def offers_audits(base_url: str) -> bool:
    return (urlsplit(base_url).hostname or "").startswith(AUDIT_HOST_PREFIX)
