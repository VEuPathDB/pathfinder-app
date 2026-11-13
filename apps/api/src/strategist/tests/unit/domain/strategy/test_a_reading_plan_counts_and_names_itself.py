from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import CombineOp

from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.reading_plan import (
    combined_ids,
    plan_lines,
    reading_label,
    reading_roles,
    reading_shape_refusal,
)

from ._builders import spec_joined, spec_leaf

_TM = Criterion(
    id="tm",
    text="tm",
    search_name="GenesByTransmembraneDomains",
    search_display_name="Transmembrane Domain Count",
    organism_param="organism",
    resolved_params={
        "organism": BoundValue(
            value=MultiPickValue(values=["Anopheles gambiae PEST"]),
            source="card",
            label="Anopheles gambiae PEST",
        ),
        "min_tm": BoundValue(value=StringValue(value="7"), source="card", label="7"),
        "max_tm": BoundValue(value=StringValue(value="7"), source="card", label="7"),
    },
)
_ORTHO = Criterion(
    id="ortho",
    text="ortho",
    search_name="GenesByOrthologPattern",
    search_display_name="Orthology Phylogenetic Profile",
    resolved_params={
        "excluded_species": BoundValue(
            value=MultiPickValue(values=["dmel"]),
            source="card",
            label="Drosophila melanogaster",
        )
    },
)


def _spec(root: StructureNode, *criteria: Criterion) -> OperationalSpec:
    return OperationalSpec(
        goal="g", criteria=list(criteria), structure=SpecStructure(root=root)
    )


def test_a_minus_keeps_the_left_genes_the_right_lacks() -> None:
    node = spec_joined(CombineOp.MINUS, spec_leaf("tm"), spec_leaf("ortho"))

    held = combined_ids(node, {"tm": frozenset("abc"), "ortho": frozenset("bz")})

    assert held == frozenset("ac")


def test_a_combine_of_three_inputs_folds_from_the_left() -> None:
    node = spec_joined(
        CombineOp.INTERSECT, spec_leaf("a"), spec_leaf("b"), spec_leaf("c")
    )
    ids = {"a": frozenset("wxy"), "b": frozenset("xyz"), "c": frozenset("y")}

    assert combined_ids(node, ids) == frozenset("y")


def test_a_union_holds_both_sides() -> None:
    node = spec_joined(CombineOp.UNION, spec_leaf("a"), spec_leaf("b"))

    assert combined_ids(node, {"a": frozenset("a"), "b": frozenset("b")}) == frozenset(
        "ab"
    )


def test_one_search_is_named_by_its_search_values_and_organism() -> None:
    label = reading_label(_spec(spec_leaf("tm"), _TM))

    assert label == "Transmembrane Domain Count: 7, 7 (Anopheles gambiae PEST)"


def test_a_combination_is_named_by_its_steps_and_operator() -> None:
    root = spec_joined(CombineOp.MINUS, spec_leaf("tm"), spec_leaf("ortho"))

    label = reading_label(_spec(root, _TM, _ORTHO))

    assert label == (
        "Transmembrane Domain Count: 7, 7 (Anopheles gambiae PEST) MINUS "
        "Orthology Phylogenetic Profile: Drosophila melanogaster"
    )


def test_a_nested_combination_is_bracketed() -> None:
    root = spec_joined(
        CombineOp.UNION,
        spec_joined(CombineOp.MINUS, spec_leaf("tm"), spec_leaf("ortho")),
        spec_leaf("ortho"),
    )

    label = reading_label(_spec(root, _TM, _ORTHO))

    assert label.startswith("(Transmembrane Domain Count")
    assert label.endswith(
        ") UNION Orthology Phylogenetic Profile: Drosophila melanogaster"
    )


@pytest.mark.parametrize(
    ("root", "refusal"),
    [
        (
            spec_joined(CombineOp.COLOCATE, spec_leaf("a"), spec_leaf("b")),
            "A reading combines searches with INTERSECT, UNION or MINUS, not COLOCATE.",
        ),
        (
            spec_joined(CombineOp.MINUS, spec_leaf("a"), spec_leaf("x")),
            "The structure names x, which is no search of this reading. Its searches are: a, b.",
        ),
        (
            spec_leaf("a"),
            "The structure leaves out b. Every search of a reading is in its structure.",
        ),
    ],
)
def test_a_reading_states_only_what_it_can_count(
    root: StructureNode, refusal: str
) -> None:
    assert reading_shape_refusal(root, ["a", "b"]) == refusal


def test_each_counted_operator_over_two_searches_is_a_plan() -> None:
    roots = [
        spec_joined(operator, spec_leaf("a"), spec_leaf("b"))
        for operator in (CombineOp.INTERSECT, CombineOp.UNION, CombineOp.MINUS)
    ]

    assert [reading_shape_refusal(root, ["a", "b"]) for root in roots] == [
        None,
        None,
        None,
    ]


def test_a_minus_seeds_its_left_and_excludes_its_right() -> None:
    root = spec_joined(
        CombineOp.UNION,
        spec_joined(CombineOp.MINUS, spec_leaf("a"), spec_leaf("b")),
        spec_leaf("c"),
    )

    assert reading_roles(root) == {"a": "seed", "b": "exclude", "c": "seed"}


def test_an_intersect_filters_its_right() -> None:
    root = spec_joined(CombineOp.INTERSECT, spec_leaf("a"), spec_leaf("b"))

    assert reading_roles(root) == {"a": "seed", "b": "filter"}


def test_a_plan_is_written_out_with_its_wire_values_and_structure() -> None:
    root = spec_joined(CombineOp.MINUS, spec_leaf("tm"), spec_leaf("ortho"))

    lines = plan_lines(_spec(root, _TM, _ORTHO))

    assert lines == [
        (
            "- tm: GenesByTransmembraneDomains (Transmembrane Domain Count), "
            'organism=["Anopheles gambiae PEST"], min_tm=7, max_tm=7'
        ),
        (
            "- ortho: GenesByOrthologPattern (Orthology Phylogenetic Profile), "
            'excluded_species=["dmel"]'
        ),
        "- structure: tm MINUS ortho",
    ]


def test_a_value_at_the_site_default_is_named_too() -> None:
    at_default = _TM.model_copy(
        update={
            "resolved_params": {
                **_TM.resolved_params,
                "min_tm": BoundValue(
                    value=StringValue(value="7"),
                    source="default",
                    label="7",
                    at_default=True,
                ),
            }
        }
    )

    label = reading_label(_spec(spec_leaf("tm"), at_default))

    assert label == "Transmembrane Domain Count: 7, 7 (Anopheles gambiae PEST)"
