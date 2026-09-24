"""The staged shape: one completed investigation, with the identity already gone.

An extract carries the request, the strategy it produced and the verification
verdict. It has no user field and no thread field, so the queue row is the only
place a staged case is associated with anybody, and promotion leaves that row
behind. Every text field is asserted redacted at construction: an extract that
still carries an identity pattern cannot be built at all.
"""

from __future__ import annotations

import hashlib

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from pydantic import ConfigDict, Field, model_validator

from pathfinder.evals.redaction import assert_redacted


class ExtractedTurn(CamelModel):
    """One exchange: what was asked, and what the assistant answered."""

    model_config = ConfigDict(frozen=True)

    request: str
    reply: str = ""


class ExtractedStrategy(CamelModel):
    """The strategy the investigation ended with."""

    model_config = ConfigDict(frozen=True)

    record_type: str | None = None
    step_count: int = 0
    structure: str = ""
    strategy_ast: JSONObject = Field(default_factory=dict)


class ExtractedVerification(CamelModel):
    """The verdict the verification phase reported."""

    model_config = ConfigDict(frozen=True)

    success: bool
    reason: str = ""
    key_findings: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    pending_checks: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True when the check succeeded and no step's check is pending."""
        return self.success and not self.pending_checks


class EvalExtract(CamelModel):
    """One candidate case, as extraction leaves it for a curator."""

    model_config = ConfigDict(frozen=True)

    site_id: str
    assistant_id: str
    turns: list[ExtractedTurn] = Field(default_factory=list)
    strategy: ExtractedStrategy | None = None
    verification: ExtractedVerification | None = None

    @model_validator(mode="after")
    def _every_text_is_redacted(self) -> EvalExtract:
        for turn in self.turns:
            assert_redacted(turn.request)
            assert_redacted(turn.reply)
        if self.verification is not None:
            assert_redacted(self.verification.reason)
            for line in (*self.verification.key_findings, *self.verification.caveats):
                assert_redacted(line)
        return self

    def content_hash(self) -> str:
        """A digest of the extract, used to stage a case once and only once."""
        payload = self.model_dump_json(by_alias=True)
        return hashlib.sha256(payload.encode()).hexdigest()


__all__ = [
    "EvalExtract",
    "ExtractedStrategy",
    "ExtractedTurn",
    "ExtractedVerification",
]
