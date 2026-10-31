from __future__ import annotations

from typing import get_args

from pathfinder.domain.evidence import WithheldEvidence, WithheldKind


def test_a_stored_review_that_withheld_a_claim_still_reads() -> None:
    held = WithheldEvidence.model_validate({"kind": "claim", "sentence": "7 of 10"})

    assert (held.kind, held.sentence) == ("claim", "7 of 10")


def test_a_check_withholds_only_genes_and_sources() -> None:
    assert get_args(WithheldKind) == ("sampled_gene", "source")
