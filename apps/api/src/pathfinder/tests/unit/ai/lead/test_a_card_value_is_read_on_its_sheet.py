"""A value a card binds is read on the published sheet of its criterion's
search, so the facts row shows a picked term with the label the site gives it."""

from __future__ import annotations

from collections.abc import Collection
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import PendingApproval, UserQuestionAnswer
from veupathdb.domain.parameters import MultiPickValue
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import lead_consult
from pathfinder.ai.lead.lead_consult import card_questions, consult_user
from pathfinder.ai.lead.turn_facts import _parameter
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import OpenQuestion, SetValues, TypedOption
from pathfinder.tests._support.recorded_searches import suite_search
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_SEARCH = "GenesByInterproDomain"
_KINASE = "Protein kinase domain (PF00069)"
_QUESTION = OpenQuestion(
    question="Which InterPro domain should the step search for?",
    options=[
        TypedOption(
            id="pf00069",
            label=_KINASE,
            binding=SetValues(
                criterion_id="c_domain", params={"domain_typeahead": "PF00069"}
            ),
        ),
        TypedOption(
            id="pf00400",
            label="WD domain, G-beta repeat (PF00400)",
            binding=SetValues(
                criterion_id="c_domain", params={"domain_typeahead": "PF00400"}
            ),
        ),
    ],
)


def _criterion() -> Criterion:
    return Criterion(
        id="c_domain",
        text="genes with a protein kinase domain",
        search_name=_SEARCH,
        resolved_params={
            "domain_database": BoundValue(
                value=MultiPickValue(values=["Pfam"]), source="stated"
            )
        },
    )


async def test_a_picked_term_shows_the_label_its_sheet_gives_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sheet = format_param_info_typed(
        suite_search("search_genes_by_interpro_domain").parameters or []
    )
    read: list[list[str]] = []

    async def _sheets(
        *, site_id: str, record_type: str | None, search_names: Collection[str]
    ) -> dict[str, list[ParameterInfo]]:
        del site_id, record_type
        read.append(sorted(search_names))
        return {_SEARCH: sheet}

    monkeypatch.setattr(lead_consult, "sheet_params_for_searches", _sheets)
    deps = lead_deps(
        pipeline_state(
            "plasmodb",
            user_message_id=uuid4(),
            domain=StrategyDomainState(
                operational_spec=OperationalSpec(criteria=[_criterion()]),
                open_questions=[_QUESTION],
            ),
        )
    )
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_card": [
            UserQuestionAnswer(
                question_id="q1", prompt=_QUESTION.question, chosen_labels=[_KINASE]
            )
        ]
    }

    await consult_user(
        run_context_for(deps, "call_card"),
        questions=card_questions([_QUESTION]),
        reply="One value decides the domain step.",
    )

    spec = deps.state.domain.operational_spec
    assert spec is not None
    [criterion] = spec.criteria
    bound = criterion.resolved_params["domain_typeahead"]
    fact = _parameter(criterion, "domain_typeahead", bound, "gene")
    assert (read, fact.value, fact.label) == (
        [[_SEARCH]],
        "PF00069",
        "Protein kinase domain",
    )
