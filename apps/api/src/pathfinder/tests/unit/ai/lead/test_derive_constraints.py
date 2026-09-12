"""Constraint grounding in the derived ledger: substitution, assumption, blocking."""

from __future__ import annotations

from veupathdb.domain.parameters import NumberValue, SinglePickValue

from pathfinder.ai.graph.state import (
    ConstraintCheck,
    PhaseDisposition,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.ledger_render import render_constraints_full
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
)
from pathfinder.domain.strategy.operational_spec import (
    AssumedValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state

_MICROARRAY_SEARCH = (
    "GenesByMicroarrayaaegLVP_AGWG_microarrayExpression_GSE22339_male_vs_female_RSRC"
)
_DERISI_PERCENTILE = "GenesByMicroarrayDerisi3D7SmoothedExpressionPercentile"
_DERISI = "GenesByMicroarrayDerisi"
_ASSUMPTION_REASON = "the request says trophozoite and this window covers 17-30 hours"


def _constraint(
    kind: ConstraintKind, value: str, source: ConstraintSource
) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        source=source,
        label="data type",
    )


def _microarray_spec(constraints: list[Constraint]) -> OperationalSpec:
    return OperationalSpec(
        goal="g",
        interpreted_goal="g",
        constraints=constraints,
        criteria=[
            Criterion(
                id="c1",
                text="microarray fold change",
                search_name=_MICROARRAY_SEARCH,
                resolved_params={"fold_change": NumberValue(value=2.0)},
            ),
        ],
    )


def _vectorbase_state(spec: OperationalSpec | None = None) -> PipelineState:
    domain = (
        StrategyDomainState()
        if spec is None
        else StrategyDomainState(operational_spec=spec)
    )
    return pipeline_state("vectorbase", domain=domain)


def _state_with_constraint(source: ConstraintSource) -> PipelineState:
    return _vectorbase_state(
        _microarray_spec(
            [_constraint(ConstraintKind.DATA_TYPE, "RNA-Seq", source)],
        ),
    )


def test_ledger_constraints_block_when_user_explicit_unmet() -> None:
    ledger = derive_ledger(_state_with_constraint(ConstraintSource.USER_EXPLICIT), None)
    assert ledger.constraints.blocking is True
    assert ledger.constraints.unmet_count == 1
    assert any(
        g.status is ConstraintStatus.SUBSTITUTED for g in ledger.constraints.grounded
    )


def test_ledger_constraints_not_blocking_for_assumed() -> None:
    ledger = derive_ledger(_state_with_constraint(ConstraintSource.ASSUMED), None)
    assert ledger.constraints.blocking is False


def test_render_summary_surfaces_blocking_constraints() -> None:
    ledger = derive_ledger(_state_with_constraint(ConstraintSource.USER_EXPLICIT), None)
    summary = ledger.render_summary()
    assert "## Constraints" in summary
    assert "blocking: True" in summary


def test_explicit_turn_constraint_overrides_assumed_spec_and_blocks() -> None:
    spec = _microarray_spec(
        [
            _constraint(
                ConstraintKind.DATA_TYPE,
                "RNA-Seq or microarray",
                ConstraintSource.ASSUMED,
            ),
        ],
    )
    intent = UserIntent(
        classification=IntentClassification.CLARIFICATION_RESPONSE,
        inferred_goal="female-enriched OBPs via RNA-Seq",
        explicit_constraints=[
            _constraint(
                ConstraintKind.DATA_TYPE,
                "RNA-Seq",
                ConstraintSource.USER_EXPLICIT,
            ),
        ],
    )

    ledger = derive_ledger(_vectorbase_state(spec), intent)

    assert ledger.constraints.blocking is True
    assert ledger.constraints.unmet_count == 1
    data_type = next(
        g
        for g in ledger.constraints.grounded
        if g.constraint.kind is ConstraintKind.DATA_TYPE
    )
    assert data_type.status is ConstraintStatus.SUBSTITUTED
    assert data_type.constraint.source is ConstraintSource.USER_EXPLICIT


def test_constraints_surface_as_provisional_when_no_spec_yet() -> None:
    intent = UserIntent(
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="x",
        explicit_constraints=[
            _constraint(
                ConstraintKind.DATA_TYPE,
                "RNA-Seq only",
                ConstraintSource.USER_EXPLICIT,
            ),
        ],
    )

    ledger = derive_ledger(_vectorbase_state(), intent)

    assert len(ledger.constraints.grounded) == 1
    assert ledger.constraints.grounded[0].status is ConstraintStatus.PROVISIONAL
    assert ledger.constraints.blocking is False


def test_verification_digest_carries_constraint_report() -> None:
    digest = VerificationDigest(
        disposition=PhaseDisposition.DONE,
        prose="p",
        reason="r",
        success=False,
        constraint_report=[
            ConstraintCheck(
                label="data type",
                requested="RNA-Seq",
                realized="microarray",
                honored=False,
                note="RNA-Seq unavailable (WDK 500); used microarray GSE22339",
            )
        ],
    )
    assert digest.constraint_report[0].honored is False


def test_operational_spec_carries_typed_constraints() -> None:
    spec = _microarray_spec(
        [
            _constraint(
                ConstraintKind.DATA_TYPE,
                "RNA-Seq",
                ConstraintSource.USER_EXPLICIT,
            ),
        ],
    )
    assert spec.constraints[0].kind is ConstraintKind.DATA_TYPE
    round_trip = OperationalSpec.model_validate(spec.model_dump(by_alias=True))
    assert round_trip.constraints[0].source is ConstraintSource.USER_EXPLICIT


def _percentile_state(bound: float) -> PipelineState:
    spec = OperationalSpec(
        goal="top 10 percent of trophozoite expression",
        interpreted_goal="top 10 percent of trophozoite expression",
        constraints=[
            Constraint(
                kind=ConstraintKind.PERCENTILE,
                requested_value="top 10%",
                label="expression percentile",
                source=ConstraintSource.USER_EXPLICIT,
            )
        ],
        criteria=[
            Criterion(
                id="c1",
                text="top 10 percent of trophozoite expression",
                search_name=_DERISI_PERCENTILE,
                resolved_params={"min_expression_percentile": NumberValue(value=bound)},
            )
        ],
    )
    return pipeline_state(domain=StrategyDomainState(operational_spec=spec))


def test_a_bound_of_80_for_top_10_percent_is_substituted() -> None:
    ledger = derive_ledger(_percentile_state(80.0), None)
    [grounded] = ledger.constraints.grounded
    assert grounded.status is ConstraintStatus.SUBSTITUTED
    assert grounded.realized_value == "80"
    assert grounded.note == "bound 80 means top 20%"
    assert ledger.constraints.blocking is True


def test_a_bound_of_90_for_top_10_percent_is_grounded() -> None:
    ledger = derive_ledger(_percentile_state(90.0), None)
    [grounded] = ledger.constraints.grounded
    assert grounded.status is ConstraintStatus.GROUNDED
    assert grounded.realized_value == "90"
    assert ledger.constraints.blocking is False


def _assumption_state() -> PipelineState:
    spec = OperationalSpec(
        goal="trophozoite expression",
        interpreted_goal="trophozoite expression",
        criteria=[
            Criterion(
                id="c1",
                text="trophozoite expression",
                search_name=_DERISI,
                resolved_params={
                    "samples_percentile_generic": SinglePickValue(value="17-30h")
                },
                assumptions=[
                    AssumedValue(
                        param_name="samples_percentile_generic",
                        value="17-30h",
                        reason=_ASSUMPTION_REASON,
                    )
                ],
            )
        ],
    )
    return pipeline_state(domain=StrategyDomainState(operational_spec=spec))


def test_an_assumed_value_is_a_grounded_non_blocking_constraint() -> None:
    ledger = derive_ledger(_assumption_state(), None)

    [grounded] = ledger.constraints.grounded
    assert grounded.constraint.kind is ConstraintKind.OTHER
    assert grounded.constraint.source is ConstraintSource.ASSUMED
    assert grounded.constraint.hard is False
    assert grounded.constraint.label == "samples_percentile_generic"
    assert grounded.constraint.requested_value == "17-30h"
    assert grounded.status is ConstraintStatus.GROUNDED
    assert grounded.realized_value == "17-30h"
    assert grounded.note == _ASSUMPTION_REASON
    assert ledger.constraints.blocking is False


def test_the_constraint_section_names_the_assumption() -> None:
    ledger = derive_ledger(_assumption_state(), None)

    rendered = render_constraints_full(ledger.constraints)

    assert "samples_percentile_generic" in rendered
    assert _ASSUMPTION_REASON in rendered
