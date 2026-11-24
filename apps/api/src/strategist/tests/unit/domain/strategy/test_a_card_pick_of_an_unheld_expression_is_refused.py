from __future__ import annotations

import pytest
from veupathdb.domain.parameters import PHYLETIC_EXPRESSION_PARAM, StringValue

from strategist.domain.strategy.card_answers import option_refusal, spec_bound_by_card
from strategist.domain.strategy.expression_handles import (
    UnknownExpressionError,
    expression_handle,
)
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from strategist.domain.strategy.question_options import SetValues

_HELD = "pfal>=1T AND hsap=0T"
_UNHELD = expression_handle("tgon>=1T")


def _spec() -> OperationalSpec:
    return OperationalSpec(
        criteria=[
            Criterion(
                id="c_groups",
                text="groups in P. falciparum and not in human",
                search_name="GroupsByPhyleticPattern",
                record_class="group",
                resolved_params={
                    PHYLETIC_EXPRESSION_PARAM: BoundValue(
                        value=StringValue(value=_HELD), source="chosen"
                    )
                },
            )
        ]
    )


def _pick() -> SetValues:
    return SetValues(
        criterion_id="c_groups", params={PHYLETIC_EXPRESSION_PARAM: _UNHELD}
    )


def test_a_pick_of_an_unheld_expression_is_refused_by_name() -> None:
    refusal = option_refusal(_spec(), _pick(), sheets={}, expressions={})

    assert refusal == f"{_UNHELD} names no held expression"


def test_binding_an_unheld_expression_raises_rather_than_keeping_the_spec() -> None:
    with pytest.raises(UnknownExpressionError) as unheld:
        spec_bound_by_card(_spec(), _pick(), option_id="o1", sheets={}, expressions={})

    assert unheld.value.handle == _UNHELD
