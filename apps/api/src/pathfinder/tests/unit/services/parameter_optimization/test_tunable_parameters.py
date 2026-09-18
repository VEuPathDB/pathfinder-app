"""The sweep grid a search's own parameter metadata supports."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import VocabOption
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.services.parameter_optimization.tunable import (
    parameter_space_for_search,
    sweep_plan,
    tunable_parameter_names,
)
from pathfinder.services.workbench.optimization import enumerate_variants


def _info(name: str, param_type: str) -> ParameterInfo:
    return ParameterInfo(
        name=name,
        display_name=name,
        type=param_type,
        required=True,
        is_visible=True,
        help="",
        value_format="",
    )


def _vocab(
    name: str,
    options: list[str],
    *,
    kind: str = "single-pick-vocabulary",
    is_visible: bool = True,
    depends_on: list[str] | None = None,
    controls: list[str] | None = None,
) -> ParameterInfo:
    info = _info(name, kind)
    info.is_visible = is_visible
    info.allowed_values = [VocabOption(value=o, display=o) for o in options]
    info.vocab_depends_on = depends_on
    info.controls_vocab_of = controls
    return info


def _number(name: str, *, bounds: tuple[float, float] | None = None) -> ParameterInfo:
    """A WDK numeric parameter: a string that carries ``isNumber``."""
    info = _info(name, "string")
    info.is_number = True
    if bounds is not None:
        info.min, info.max = bounds
    return info


def test_a_vocabulary_parameter_becomes_a_categorical_spec() -> None:
    specs = parameter_space_for_search(
        "GenesByExonCount",
        [_vocab("scope", ["gene", "transcript"])],
        budget=30,
    )

    assert [(s.name, s.param_type, s.choices) for s in specs] == [
        ("scope", "categorical", ["gene", "transcript"])
    ]


def test_a_bounded_number_parameter_becomes_a_numeric_spec() -> None:
    specs = parameter_space_for_search(
        "GenesByMolecularWeight",
        [_number("weight", bounds=(10.0, 50.0))],
        budget=30,
    )

    assert [(s.name, s.param_type, s.min, s.max) for s in specs] == [
        ("weight", "numeric", 10.0, 50.0)
    ]


def test_a_number_parameter_without_bounds_is_not_tunable() -> None:
    with pytest.raises(ValueError, match="GenesByMolecularWeight") as refusal:
        parameter_space_for_search(
            "GenesByMolecularWeight",
            [_number("min_molecular_weight")],
            budget=30,
        )

    assert "no tunable parameters" in str(refusal.value)


def test_a_mixed_search_yields_one_spec_per_tunable_parameter() -> None:
    specs = parameter_space_for_search(
        "GenesByExonCount",
        [
            _vocab("organism", ["pf", "pv"], kind="multi-pick-vocabulary"),
            _vocab("scope", ["gene", "transcript"]),
            _number("num_exons", bounds=(1.0, 9.0)),
            _info("gene_result", "input-step"),
        ],
        budget=100,
    )

    assert [s.name for s in specs] == ["organism", "scope", "num_exons"]


def test_a_hidden_parameter_is_never_swept() -> None:
    with pytest.raises(ValueError, match="no tunable parameters"):
        parameter_space_for_search(
            "GenesByText",
            [_vocab("timestamp", ["a", "b"], is_visible=False)],
            budget=30,
        )


def test_named_parameters_narrow_the_grid() -> None:
    specs = parameter_space_for_search(
        "GenesByExonCount",
        [
            _vocab("organism", ["pf", "pv"], kind="multi-pick-vocabulary"),
            _vocab("scope", ["gene", "transcript"]),
        ],
        names=["scope"],
        budget=30,
    )

    assert [s.name for s in specs] == ["scope"]


def test_a_named_parameter_that_is_not_tunable_is_refused() -> None:
    with pytest.raises(ValueError, match="phyletic_term") as refusal:
        parameter_space_for_search(
            "GenesByExonCount",
            [_vocab("scope", ["gene", "wide"])],
            names=["phyletic_term"],
            budget=30,
        )

    assert "scope" in str(refusal.value)


def test_the_grid_never_exceeds_the_budget() -> None:
    specs = parameter_space_for_search(
        "GenesByLocation",
        [
            _vocab(
                "organism",
                [f"o{i}" for i in range(48)],
                kind="multi-pick-vocabulary",
            ),
            _vocab("chromosome", [f"c{i}" for i in range(15)]),
        ],
        budget=30,
    )

    assert len(enumerate_variants(specs, {})) <= 30


def test_a_budget_below_the_narrowest_grid_keeps_one_parameter() -> None:
    specs = parameter_space_for_search(
        "GenesByLocation",
        [
            _vocab("a", ["1", "2"]),
            _vocab("b", ["1", "2"]),
            _vocab("c", ["1", "2"]),
        ],
        budget=4,
    )

    assert len(enumerate_variants(specs, {})) <= 4
    assert [s.name for s in specs] == ["a", "b"]


def test_a_numeric_grid_is_thinned_rather_than_dropped() -> None:
    specs = parameter_space_for_search(
        "GenesByMolecularWeight",
        [
            _number("weight", bounds=(0.0, 100.0)),
            _vocab("scope", ["a", "b", "c"]),
        ],
        budget=6,
    )

    assert [s.name for s in specs] == ["weight", "scope"]
    assert len(enumerate_variants(specs, {})) <= 6


def test_tunable_names_are_the_names_of_the_derived_specs() -> None:
    parameters = [
        _vocab("organism", ["pf", "pv"], kind="multi-pick-vocabulary"),
        _info("gene_result", "input-step"),
    ]

    assert tunable_parameter_names(parameters) == ["organism"]


def test_a_search_with_nothing_tunable_names_no_parameter() -> None:
    assert tunable_parameter_names([_info("gene_result", "input-step")]) == []


def test_a_multi_pick_parameter_sweeps_one_term_in_its_own_wire_shape() -> None:
    specs = parameter_space_for_search(
        "GenesByExonCount",
        [_vocab("organism", ["pf", "pv"], kind="multi-pick-vocabulary")],
        budget=30,
    )

    wires = [v.params["organism"].to_wire() for v in enumerate_variants(specs, {})]

    assert wires == ['["pf"]', '["pv"]']


def test_a_single_pick_parameter_sweeps_the_bare_term() -> None:
    specs = parameter_space_for_search(
        "GenesByExonCount",
        [_vocab("scope", ["gene", "transcript"])],
        budget=30,
    )

    wires = [v.params["scope"].to_wire() for v in enumerate_variants(specs, {})]

    assert wires == ["gene", "transcript"]


def test_a_dependent_child_is_never_swept() -> None:
    parameters = [
        _vocab("organism", ["pf", "pv"], kind="multi-pick-vocabulary"),
        _vocab("strain", ["3D7", "HB3"], depends_on=["organism"]),
    ]

    assert tunable_parameter_names(parameters) == ["organism"]


def test_a_parameter_that_decides_another_vocabulary_is_never_swept() -> None:
    parameters = [
        _vocab(
            "organism",
            ["pf", "pv"],
            kind="multi-pick-vocabulary",
            controls=["strain"],
        ),
        _vocab("strain", ["3D7", "HB3"], depends_on=["organism"]),
    ]

    assert tunable_parameter_names(parameters) == []


def test_a_search_whose_only_enum_is_dependent_is_refused() -> None:
    with pytest.raises(ValueError, match="GenesByStrain") as refusal:
        parameter_space_for_search(
            "GenesByStrain",
            [_vocab("strain", ["3D7", "HB3"], depends_on=["organism"])],
            budget=30,
        )

    assert "strain depends on another parameter" in str(refusal.value)


def test_an_unbounded_numeric_refusal_says_wdk_states_no_bounds() -> None:
    with pytest.raises(ValueError, match="GenesByMolecularWeight") as refusal:
        parameter_space_for_search(
            "GenesByMolecularWeight",
            [
                _number("min_molecular_weight"),
                _number("max_molecular_weight"),
            ],
            budget=30,
        )

    assert "WDK states no bounds for min_molecular_weight, max_molecular_weight" in str(
        refusal.value
    )


def test_thinning_keeps_the_steps_own_value() -> None:
    specs = parameter_space_for_search(
        "GenesByTaxon",
        [
            _vocab(
                "organism",
                [f"o{i}" for i in range(10)],
                kind="multi-pick-vocabulary",
            )
        ],
        budget=3,
        current_values={"organism": '["o7"]'},
    )

    assert specs[0].choices == ["o7", "o0", "o1"]


def test_the_plan_keeps_the_steps_own_value_in_the_grid() -> None:
    plan = sweep_plan(
        "GenesByTaxon",
        [
            _vocab(
                "organism",
                [f"o{i}" for i in range(10)],
                kind="multi-pick-vocabulary",
            )
        ],
        {"organism": '["o7"]'},
        budget=3,
    )

    assert (plan.parameter_space[0].choices or [])[0] == "o7"


def test_a_request_that_names_no_parameter_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="GenesByExonCount") as refusal:
        parameter_space_for_search(
            "GenesByExonCount",
            [_vocab("scope", ["gene", "wide"])],
            names=[],
            budget=30,
        )

    assert "names no parameter to vary" in str(refusal.value)


def test_a_budget_below_two_trials_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="GenesByExonCount") as refusal:
        parameter_space_for_search(
            "GenesByExonCount",
            [_vocab("scope", ["gene", "wide"])],
            budget=1,
        )

    assert "budget of 1" in str(refusal.value)
