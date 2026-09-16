"""A gene set names its current membership on the wire.

The client holds an evaluation and the set it belongs to, so the digest is
what tells it whether the two still describe each other.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pathfinder.services.gene_sets.types import GeneSet, GeneSetMembership
from pathfinder.transport.http.routers.gene_sets._shared import to_response

_GENES = ["PF3D7_0100100", "PF3D7_0200200", "PF3D7_0304600"]


def _set(gene_ids: list[str]) -> GeneSet:
    return GeneSet(
        id="gs-gametocyte-secreted",
        user_id=uuid4(),
        site_id="plasmodb",
        name="gametocyte secreted",
        gene_ids=gene_ids,
        source="strategy",
        created_at=datetime(2026, 9, 15, tzinfo=UTC),
    )


def test_the_response_carries_the_digest_of_the_genes_it_holds() -> None:
    response = to_response(_set(_GENES))

    assert response.gene_count == 3
    assert response.membership_digest == GeneSetMembership.of(_GENES).digest


def test_two_sets_of_the_same_size_answer_different_digests() -> None:
    one = to_response(_set(["PF3D7_0100100", "PF3D7_0200200"]))
    other = to_response(_set(["PF3D7_0100100", "PF3D7_0304600"]))

    assert one.gene_count == other.gene_count == 2
    assert one.membership_digest != other.membership_digest


def test_a_membership_that_grows_answers_a_new_digest() -> None:
    before = to_response(_set(_GENES))
    after = to_response(_set([*_GENES, "PF3D7_0930300"]))

    assert before.membership_digest != after.membership_digest
