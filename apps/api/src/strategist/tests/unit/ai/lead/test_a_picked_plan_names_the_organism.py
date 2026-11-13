from __future__ import annotations

from collections.abc import Iterator

import pytest
from veupathdb.domain.parameters import MultiPickValue
from veupathdb_mcp.catalog import (
    DecisionRequest,
    DecisionResponse,
    post_decision,
    use_decisions_transport,
)

from strategist.ai.lead.held_intent import hold_the_intent
from strategist.ai.lead.intent import IntentClassification, UserIntent
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    OrganismValue,
)
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.organism_picks import organism_questions
from strategist.domain.strategy.reading_plan import OfferedReading, build_message
from strategist.platform.config import get_settings
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_SPECIES = "Plasmodium falciparum"
_STRAIN = "Plasmodium falciparum 3D7"
_TITLE = f"{_SPECIES} genes with a signal peptide"
_ASKED = f"Which {_SPECIES} genes carry a signal peptide?"


async def _unanswered(request: DecisionRequest) -> DecisionResponse | None:
    del request
    return None


@pytest.fixture
def _unanswered_service(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(get_settings(), "strategist_chat_provider", "default")
    use_decisions_transport(_unanswered)
    yield
    use_decisions_transport(post_decision)


def _plan(organism: str) -> OfferedReading:
    criterion = Criterion(
        id="peptide",
        text="peptide",
        search_name="GenesWithSignalPeptide",
        organism_param="organism",
        resolved_params={
            "organism": BoundValue(
                value=MultiPickValue(values=[organism]), source="card", label=organism
            )
        },
    )
    spec = OperationalSpec(
        criteria=[criterion],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="peptide")
        ),
    )
    return OfferedReading(label=_TITLE, plan=_TITLE, gene_count=479, spec=spec)


def _intent() -> UserIntent:
    return UserIntent(
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="[test] organism",
        explicit_constraints=[
            Constraint(
                kind=ConstraintKind.ORGANISM,
                requested_value=_SPECIES,
                label="organism",
                source=ConstraintSource.USER_EXPLICIT,
                quote=_SPECIES,
                value=OrganismValue(organism=_SPECIES),
            )
        ],
    )


@pytest.mark.usefixtures("recorded_site_organisms", "_unanswered_service")
async def test_the_picked_plan_names_the_organism_the_request_left_open() -> None:
    message = build_message(_TITLE)
    deps = lead_deps(pipeline_state("plasmodb", user_prompt=message))
    deps.state.domain.offer_reading(_plan(_STRAIN))

    await hold_the_intent(deps, _intent(), message)

    domain = deps.state.domain
    assert [c.organism for c in domain.requirements] == [_STRAIN]
    assert organism_questions(domain.requirements, domain.organism_picks) == []


@pytest.mark.usefixtures("recorded_site_organisms", "_unanswered_service")
async def test_without_a_picked_plan_the_organism_is_asked() -> None:
    message = _ASKED
    deps = lead_deps(pipeline_state("plasmodb", user_prompt=message))
    deps.state.domain.offer_reading(_plan(_STRAIN))

    await hold_the_intent(deps, _intent(), message)

    domain = deps.state.domain
    assert [c.organism for c in domain.requirements] == [None]
    assert len(organism_questions(domain.requirements, domain.organism_picks)) == 1
