"""What the validator every push runs refuses.

Two of the guards catch strategies that run fine and answer nothing: a
differential search whose reference and comparison samples are the same group
is a contrast of a set against itself, and INTERSECT across organisms compares
gene IDs from different species, which never match.
"""

from __future__ import annotations

from pathfinder.domain.parameters.values import MultiPickValue, StringValue
from pathfinder.domain.strategy.ast import StrategyStepNode
from pathfinder.domain.strategy.ops import CombineOp
from pathfinder.domain.strategy.validate import (
    StrategyValidator,
    ValidationResult,
    validate_strategy,
)

from ._builders import combine


def _text_leaf(search_name: str = "GenesByText") -> StrategyStepNode:
    return StrategyStepNode(
        id="leaf",
        search_name=search_name,
        parameters={"text_expression": StringValue(value="kinase")},
    )


def _verdict(result: ValidationResult) -> tuple[bool, list[str]]:
    return result.valid, [issue.code for issue in result.errors]


def _differential(ref: str, comp: str) -> StrategyStepNode:
    return StrategyStepNode(
        id="s",
        search_name="GenesByDeseqExpression",
        parameters={
            "samples_de_ref_generic_deseq": StringValue(value=ref),
            "samples_de_comp_generic_deseq": StringValue(value=comp),
        },
    )


def _taxon(step_id: str, organism: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByTaxon",
        parameters={"organism": MultiPickValue(values=[organism])},
    )


_PF = "Plasmodium falciparum 3D7"
_TG = "Toxoplasma gondii ME49"


class TestTheStructuralChecks:
    def test_valid_leaf_passes(self) -> None:
        assert _verdict(validate_strategy(_text_leaf(), "transcript")) == (True, [])

    def test_empty_search_name_is_missing_search_name(self) -> None:
        result = validate_strategy(_text_leaf(search_name=""), "transcript")

        assert _verdict(result) == (False, ["MISSING_SEARCH_NAME"])
        assert result.errors[0].path == "root.searchName"

    def test_empty_record_type_is_missing_record_type(self) -> None:
        result = validate_strategy(_text_leaf(), "")

        assert _verdict(result) == (False, ["MISSING_RECORD_TYPE"])
        assert result.errors[0].path == "recordType"


class TestTheSearchCatalog:
    def test_unknown_search_when_catalog_provided(self) -> None:
        validator = StrategyValidator(
            available_searches={"transcript": ["GenesByText", "GenesByGoTerm"]},
        )

        result = validator.validate(
            _text_leaf(search_name="NotARealSearch"), "transcript"
        )

        assert _verdict(result) == (False, ["UNKNOWN_SEARCH"])
        assert result.errors[0].message == "Unknown search: NotARealSearch"
        assert result.errors[0].path == "root.searchName"

    def test_known_search_in_catalog_passes(self) -> None:
        validator = StrategyValidator(
            available_searches={"transcript": ["GenesByText"]}
        )

        assert _verdict(validator.validate(_text_leaf(), "transcript")) == (True, [])

    def test_search_valid_for_other_record_type_is_unknown_here(self) -> None:
        validator = StrategyValidator(
            available_searches={
                "gene": ["GenesByText"],
                "transcript": ["GenesByGoTerm"],
            },
        )

        result = validator.validate(_text_leaf(), "transcript")

        assert _verdict(result) == (False, ["UNKNOWN_SEARCH"])


class TestIdenticalContrastSamples:
    def test_a_group_contrasted_against_itself_is_rejected(self) -> None:
        result = validate_strategy(
            _differential("gametocyte", "gametocyte"), "transcript"
        )

        assert _verdict(result) == (False, ["IDENTICAL_CONTRAST_SAMPLES"])
        assert result.errors[0].path == ("root.parameters.samples_de_ref_generic_deseq")

    def test_the_message_names_the_problem_in_biological_terms(self) -> None:
        result = validate_strategy(
            _differential("gametocyte", "gametocyte"), "transcript"
        )

        joined = " ".join(issue.message for issue in result.errors)
        assert "reference" in joined.lower()
        assert "comparison" in joined.lower()

    def test_a_genuine_contrast_passes(self) -> None:
        result = validate_strategy(_differential("gametocyte", "ring"), "transcript")

        assert _verdict(result) == (True, [])

    def test_fold_change_naming_is_covered_too(self) -> None:
        """The pair is matched by ``_ref_``/``_comp_``, not one search's names."""
        step = StrategyStepNode(
            id="s",
            search_name="GenesByFoldChange",
            parameters={
                "samples_fc_ref_generic": StringValue(value="ring"),
                "samples_fc_comp_generic": StringValue(value="ring"),
            },
        )

        assert _verdict(validate_strategy(step, "transcript")) == (
            False,
            ["IDENTICAL_CONTRAST_SAMPLES"],
        )

    def test_an_unpaired_reference_is_not_flagged(self) -> None:
        step = StrategyStepNode(
            id="s",
            search_name="GenesByDeseqExpression",
            parameters={"samples_de_ref_generic_deseq": StringValue(value="ring")},
        )

        assert _verdict(validate_strategy(step, "transcript")) == (True, [])


class TestCrossOrganismIntersect:
    def test_intersecting_two_species_is_rejected(self) -> None:
        step = combine("c", _taxon("a", _PF), _taxon("b", _TG))

        result = validate_strategy(step, "transcript")

        assert _verdict(result) == (False, ["CROSS_ORGANISM_INTERSECT"])
        assert result.errors[0].path == "root.operator"

    def test_the_message_explains_why_it_returns_zero(self) -> None:
        step = combine("c", _taxon("a", _PF), _taxon("b", _TG))

        joined = " ".join(
            issue.message for issue in validate_strategy(step, "transcript").errors
        )

        assert "organism" in joined.lower()

    def test_the_same_organism_on_both_sides_passes(self) -> None:
        step = combine("c", _taxon("a", _PF), _taxon("b", _PF))

        assert _verdict(validate_strategy(step, "transcript")) == (True, [])

    def test_an_unknown_organism_scope_is_not_guessed_at(self) -> None:
        """The guard fires only when both sides are known and disjoint."""
        step = combine(
            "c", _taxon("a", _PF), StrategyStepNode(id="b", search_name="GenesByText")
        )

        assert _verdict(validate_strategy(step, "transcript")) == (True, [])

    def test_a_union_across_organisms_is_allowed(self) -> None:
        """UNION across species is meaningful; only INTERSECT is always zero."""
        step = combine("c", _taxon("a", _PF), _taxon("b", _TG), CombineOp.UNION)

        assert _verdict(validate_strategy(step, "transcript")) == (True, [])
