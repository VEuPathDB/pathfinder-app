"""An intron-support answer names the error its verdict carries, or says why it judges none."""

from __future__ import annotations

from typing import get_args

import pytest
from pydantic import TypeAdapter
from veupathdb_mcp.audit import IntronVerdict

from pathfinder.domain.audit.confirmations import Confirmation, IntronConfirmation
from pathfinder.domain.audit.findings import (
    NO_ERROR,
    Classification,
    ConfirmationEvidence,
    classify_confirmation,
)
from pathfinder.tests._support.audit_introns import intron_audit

_CONFIRMATION: TypeAdapter[Confirmation] = TypeAdapter(Confirmation)
_SHIFTED = Classification(error_type="shifted_splice_site", certainty="medium")
_SPURIOUS = Classification(error_type="spurious_intron", certainty="medium")
_NAMED: dict[str, Classification] = {
    "SUPPORTED": NO_ERROR,
    "UNSUPPORTED_MISSING_EXON": Classification(
        error_type="missing_exon", certainty="high"
    ),
    "UNSUPPORTED_SHIFTED": _SHIFTED,
    "UNSUPPORTED_REPLACED": _SHIFTED,
    "UNSUPPORTED_NONCANONICAL": _SPURIOUS,
    "UNSUPPORTED_RETAINED": _SPURIOUS,
    "UNSUPPORTED_UNEXPLAINED": Classification(
        error_type="unsupported_intron", certainty="low"
    ),
}
_UNJUDGED = {
    "NOT_EXPRESSED": "NOT_EXPRESSED: the gene's reads are below the expression gate",
    "NOT_CHECKED": "NOT_CHECKED: the site serves no junction track",
}


def test_every_intron_verdict_is_classified() -> None:
    assert sorted([*_NAMED, *_UNJUDGED]) == sorted(get_args(IntronVerdict.__value__))


@pytest.mark.parametrize(("verdict", "named"), sorted(_NAMED.items()))
def test_an_intron_verdict_names_its_error(
    verdict: IntronVerdict, named: Classification
) -> None:
    confirmation = IntronConfirmation(result=intron_audit(verdict))
    assert classify_confirmation(confirmation) == named
    assert confirmation.verdict == verdict


@pytest.mark.parametrize(("verdict", "said"), sorted(_UNJUDGED.items()))
def test_an_unjudged_intron_verdict_says_why(verdict: IntronVerdict, said: str) -> None:
    named = classify_confirmation(IntronConfirmation(result=intron_audit(verdict)))
    assert (named.error_type, named.judged) == (None, False)
    assert named.message is not None
    assert named.message.startswith(said)


def test_a_stored_confirmation_tells_a_replaced_intron_from_a_shifted_one() -> None:
    stored = [
        ConfirmationEvidence(
            confirmation=IntronConfirmation(result=intron_audit(verdict))
        ).model_dump(mode="json", by_alias=True)
        for verdict in ("UNSUPPORTED_SHIFTED", "UNSUPPORTED_REPLACED")
    ]
    read = [_CONFIRMATION.validate_python(row["confirmation"]) for row in stored]
    assert [c.check for c in read] == ["intron_support", "intron_support"]
    assert [c.verdict for c in read] == ["UNSUPPORTED_SHIFTED", "UNSUPPORTED_REPLACED"]
    assert [classify_confirmation(c) for c in read] == [_SHIFTED, _SHIFTED]
