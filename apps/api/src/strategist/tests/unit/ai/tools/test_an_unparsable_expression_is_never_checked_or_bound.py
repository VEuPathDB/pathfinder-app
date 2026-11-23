from __future__ import annotations

import pytest
from veupathdb.domain.parameters import (
    PHYLETIC_EXPRESSION_PARAM,
    PhyleticExpression,
    StringValue,
)
from veupathdb.errors import ValidationError

from strategist.ai.agents.frame_expression_checks import _expressions
from strategist.ai.tools.standalone import _expression_check
from strategist.ai.tools.standalone._expression_check import read_expression_fit
from strategist.domain.expression_fit import bound_expressions
from strategist.domain.strategy.card_answers import option_refusal
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from strategist.domain.strategy.question_options import SetValues

_UNPARSABLE = "not a pattern at all"
_STEP = 227355040


def _criterion(expression: str) -> Criterion:
    return Criterion(
        id="c_groups",
        text="groups in P. falciparum",
        search_name="GroupsByPhyleticPattern",
        record_class="group",
        resolved_params={
            PHYLETIC_EXPRESSION_PARAM: BoundValue(
                value=StringValue(value=expression), source="chosen"
            )
        },
    )


def test_the_grammar_the_site_parses_refuses_it() -> None:
    with pytest.raises(ValidationError):
        PhyleticExpression.parse(_UNPARSABLE)


def test_a_card_refuses_to_bind_it() -> None:
    spec = OperationalSpec(criteria=[_criterion("pfal>=1T")])

    refusal = option_refusal(
        spec,
        SetValues(
            criterion_id="c_groups", params={PHYLETIC_EXPRESSION_PARAM: _UNPARSABLE}
        ),
        sheets={},
        expressions={},
    )

    assert refusal is not None
    assert "is not a value of phyletic_expression" in refusal


async def test_a_held_one_reads_no_groups_and_states_no_fit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _no_site(_site_id: str) -> object:
        raise AssertionError

    monkeypatch.setattr(_expression_check, "get_strategy_api", _no_site)
    criterion = _criterion(_UNPARSABLE)

    fit = await read_expression_fit("orthomcl", _STEP, criterion)

    assert fit is None
    assert bound_expressions([criterion], {"c_groups": _STEP}) == {}
    assert _expressions([criterion]) == []
