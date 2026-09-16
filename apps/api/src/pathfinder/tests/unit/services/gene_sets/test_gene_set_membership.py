"""The identity a gene set's membership answers to.

A count cannot tell two different sets of the same size apart, so the
membership names itself with a digest of the gene ids it holds.
"""

from __future__ import annotations

from pathfinder.services.gene_sets.types import GeneSetMembership

_GENES = ["PF3D7_0100100", "PF3D7_0200200", "PF3D7_0304600"]


class TestTheDigestNamesTheMembership:
    def test_order_does_not_change_the_digest(self) -> None:
        first = GeneSetMembership.of(_GENES)
        shuffled = GeneSetMembership.of(list(reversed(_GENES)))

        assert first.digest == shuffled.digest

    def test_a_repeated_gene_does_not_change_the_digest(self) -> None:
        plain = GeneSetMembership.of(_GENES)
        repeated = GeneSetMembership.of([*_GENES, "PF3D7_0100100"])

        assert repeated.digest == plain.digest
        assert repeated.gene_count == 3

    def test_two_sets_of_the_same_size_differ(self) -> None:
        one = GeneSetMembership.of(["PF3D7_0100100", "PF3D7_0200200"])
        other = GeneSetMembership.of(["PF3D7_0100100", "PF3D7_0304600"])

        assert one.gene_count == other.gene_count == 2
        assert one.digest != other.digest

    def test_one_gene_more_changes_the_digest(self) -> None:
        before = GeneSetMembership.of(_GENES)
        after = GeneSetMembership.of([*_GENES, "PF3D7_0930300"])

        assert before.gene_count == 3
        assert after.gene_count == 4
        assert before.digest != after.digest

    def test_an_empty_membership_counts_nothing(self) -> None:
        empty = GeneSetMembership.of([])

        assert empty.gene_count == 0
        assert empty.digest != GeneSetMembership.of(_GENES).digest
