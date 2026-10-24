"""OrthoMCL's phyletic expression is written to a grammar, so it is never a text
query and never a phrase the researcher must have typed."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import (
    PhyleticTree,
    StringValue,
    TaxonEntry,
)
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.domain.strategy.expression_handles import expression_handle
from pathfinder.domain.strategy.operational_spec import BoundValue, Measurement
from pathfinder.services.strategies.measurements import (
    MeasuredBinding,
    TurnCounts,
    measure_binding,
)
from pathfinder.services.strategies.parameter_rules import (
    parameter_class,
    rules_of,
    text_query,
)


def _expression() -> ParameterInfo:
    return ParameterInfo.model_validate(
        {
            "name": "phyletic_expression",
            "display_name": "Expression",
            "type": "string",
            "required": True,
            "is_visible": True,
            "help": "",
            "value_format": "",
        }
    )


def test_the_expression_is_its_own_class() -> None:
    assert parameter_class(_expression()) == "phyletic_expression"


def test_the_expression_is_no_text_query() -> None:
    bound = BoundValue(
        value=StringValue(value="pfal>=1T AND pfag+pfhb<=1T"), source="stated"
    )

    assert not text_query(_expression(), bound)


def test_the_expression_is_read_back_in_words() -> None:
    assert rules_of(_expression()).measurement == "expression_reading"


def _tree() -> PhyleticTree:
    return PhyleticTree.from_taxa(
        [
            TaxonEntry(
                id="3",
                parent_id=None,
                code="pfal",
                label="P. falciparum 3D7",
                clade=False,
            ),
            TaxonEntry(
                id="4",
                parent_id=None,
                code="pfag",
                label="P. falciparum 7G8",
                clade=False,
            ),
            TaxonEntry(
                id="5",
                parent_id=None,
                code="pfhb",
                label="P. falciparum HB3",
                clade=False,
            ),
        ]
    )


@pytest.mark.parametrize("count", [277, None])
async def test_the_reading_states_the_list_size_whether_or_not_the_site_counted(
    count: int | None,
) -> None:
    expression = "pfal=1 AND pfag+pfhb<=1T"

    measured = await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="orthomcl",
            record_type="group",
            search_name="GroupsByPhyleticPattern",
            params={"phyletic_expression": StringValue(value=expression)},
            count=count,
        ),
        values={
            "phyletic_expression": BoundValue(
                value=StringValue(value=expression), source="chosen"
            )
        },
        infos=[_expression()],
        tree=_tree(),
    )

    assert measured == [
        Measurement(
            kind="vocabulary_label",
            param="phyletic_expression",
            reading=expression_handle(expression),
            label=(
                "exactly 1 protein of P. falciparum 3D7 and at most 1 genome of "
                "these 2: P. falciparum 7G8, P. falciparum HB3 (2 genomes of 1 "
                "species; P. falciparum 2)"
            ),
        )
    ]
