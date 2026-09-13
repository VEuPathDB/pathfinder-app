"""A stated combination read over criteria a combine cannot hold.

A transform stands on the path to the root and an exclusion is subtracted from
a branch, so the operator is read over the members that remain.
"""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.combination_check import (
    first_combination_violation,
    match_terms,
)
from pathfinder.domain.strategy.constraints import (
    CombinationRequest,
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    SpecStructure,
    StructureNode,
)

from ._builders import spec_joined, spec_leaf

_MASS_SPEC = Criterion(
    id="c_ms",
    text="trophozoite mass spectrometry evidence",
    search_name="GenesByMassSpec",
)
_DERISI = Criterion(
    id="c_derisi",
    text="DeRisi timecourse expression",
    search_name="GenesByRNASeqEvidence",
)


def _requirement(value: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.COMBINATION,
        requested_value=value,
        label="how the evidence combines",
        source=ConstraintSource.USER_EXPLICIT,
    )


def _breach_message(
    requirements: list[Constraint],
    criteria: list[Criterion],
    structure: SpecStructure,
) -> str:
    """The first breach's message, empty when no requirement is breached."""
    breach = first_combination_violation(requirements, criteria, structure)
    return "" if breach is None else breach.message


_SIGNAL = Criterion(
    id="c_signal",
    text="Toxoplasma gondii ME49 genes with a predicted signal peptide",
    search_name="GenesWithSignalPeptide",
    role="seed",
)
_ORTHOLOG_MAP = Criterion(
    id="c_ortho",
    text="Plasmodium falciparum 3D7 orthologs of the input genes",
    search_name="GenesByOrthologs",
    role="transform",
)
_GAMETOCYTE = Criterion(
    id="c_gam",
    text="expressed in the top 20% during gametocyte stages",
    search_name="GenesByRNASeqEvidence",
    role="filter",
)
_EXCLUDE_CRYPTO = Criterion(
    id="c_crypto",
    text="has an ortholog in Cryptosporidium parvum Iowa II",
    search_name="GenesByOrthologPhyleticPattern",
    role="exclude",
)
_MAPPED = [_SIGNAL, _ORTHOLOG_MAP, _GAMETOCYTE, _EXCLUDE_CRYPTO]
_AND_FOUR = (
    "predicted signal peptide AND "
    "transform to Plasmodium falciparum 3D7 orthologs AND "
    "top 20% expressed during gametocyte stages AND "
    "remove any with a Cryptosporidium parvum Iowa II ortholog"
)


def _mapped_tree(inner: CombineOp) -> SpecStructure:
    """``((transform(signal) <inner> gametocyte) INTERSECT exclude_crypto)``."""
    return SpecStructure(
        root=spec_joined(
            CombineOp.INTERSECT,
            spec_joined(
                inner,
                StructureNode(
                    kind="transform",
                    criterion_id="c_ortho",
                    inputs=[spec_leaf("c_signal")],
                ),
                spec_leaf("c_gam"),
            ),
            spec_leaf("c_crypto"),
        )
    )


class TestAStatementThatNamesATransformCriterion:
    """A transform is a node on the path, so no combine can bring it."""

    def test_a_term_that_names_a_transform_is_no_member_of_the_combine(self) -> None:
        request = CombinationRequest.parse(_AND_FOUR)
        assert request is not None

        matched = match_terms(request.terms, _MAPPED)

        assert matched is not None
        assert sorted(matched.members.values()) == ["c_gam", "c_signal"]
        assert list(matched.transforms.values()) == ["c_ortho"]
        assert list(matched.excludes.values()) == ["c_crypto"]

    def test_the_tree_the_request_describes_is_no_violation(self) -> None:
        assert (
            _breach_message(
                [_requirement(_AND_FOUR)], _MAPPED, _mapped_tree(CombineOp.INTERSECT)
            )
            == ""
        )

    def test_the_same_statement_over_a_union_of_the_filters_is_refused(self) -> None:
        message = _breach_message(
            [_requirement(_AND_FOUR)], _MAPPED, _mapped_tree(CombineOp.UNION)
        )

        assert "must meet at INTERSECT" in message
        assert "joins them at UNION" in message

    def test_a_statement_of_one_filter_and_one_transform_abstains(self) -> None:
        """One member joins nothing, so the statement gates no combine."""
        assert (
            _breach_message(
                [
                    _requirement(
                        "predicted signal peptide AND "
                        "transform to Plasmodium falciparum 3D7 orthologs"
                    )
                ],
                _MAPPED,
                _mapped_tree(CombineOp.UNION),
            )
            == ""
        )


_AND_REMOVE = (
    "mass spectrometry evidence AND DeRisi expression AND "
    "remove any with a Cryptosporidium parvum Iowa II ortholog"
)
_REMOVING = [_MASS_SPEC, _DERISI, _EXCLUDE_CRYPTO]


class TestAStatementThatRemovesACriterion:
    """An exclusion is subtracted from the branch, and joins no combine of it."""

    def test_a_removed_criterion_is_no_member_of_the_combine(self) -> None:
        request = CombinationRequest.parse(_AND_REMOVE)
        assert request is not None

        matched = match_terms(request.terms, _REMOVING)

        assert matched is not None
        assert sorted(matched.members.values()) == ["c_derisi", "c_ms"]
        assert list(matched.excludes.values()) == ["c_crypto"]

    def test_a_minus_over_the_intersect_is_no_violation(self) -> None:
        structure = SpecStructure(
            root=spec_joined(
                CombineOp.MINUS,
                spec_joined(
                    CombineOp.INTERSECT, spec_leaf("c_ms"), spec_leaf("c_derisi")
                ),
                spec_leaf("c_crypto"),
            )
        )

        assert _breach_message([_requirement(_AND_REMOVE)], _REMOVING, structure) == ""

    def test_a_union_under_the_minus_is_still_refused(self) -> None:
        structure = SpecStructure(
            root=spec_joined(
                CombineOp.MINUS,
                spec_joined(CombineOp.UNION, spec_leaf("c_ms"), spec_leaf("c_derisi")),
                spec_leaf("c_crypto"),
            )
        )

        message = _breach_message([_requirement(_AND_REMOVE)], _REMOVING, structure)

        assert "must meet at INTERSECT" in message
        assert "UNION" in message
