"""A build reads what each step it binds runs on, so the ledger grounds a
data-type requirement before any check runs."""

from __future__ import annotations

from typing import Any

import pytest

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import sub_agent_dispatch
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.sub_agent_dispatch import build_strategy
from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import ConstraintKind, ConstraintStatus
from pathfinder.domain.strategy.data_marks import DataMarks
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.strategies import bound_uploads
from pathfinder.services.strategies.user_dataset_searches import OwnedUpload
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests._support.user_dataset_doubles import UPLOAD_DATASET
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

_PERCENTILE = "GenesByRNASeqpfal3D7_Gomez-Diaz_asexual_stages_ebi_rnaSeq_RSRCPercentile"


def _built(criterion: Criterion) -> Any:
    spec = OperationalSpec(
        goal="RNA-Seq genes",
        criteria=[criterion],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id=criterion.id)
        ),
    )
    state = pipeline_state(
        user_prompt="build it", domain=StrategyDomainState(operational_spec=spec)
    )
    state.domain.requirements = [
        requirement(ConstraintKind.DATA_TYPE, "RNA-Seq dataset", "RNA-Seq")
    ]
    return run_context_for(
        lead_deps(state, strategy_session=StrategySession(site_id="plasmodb"))
    )


@pytest.fixture(autouse=True)
def _pushed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_build(**kwargs: Any) -> BuildOutcome:
        return BuildOutcome(pushed_step_ids=[kwargs["root"].id])

    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _fake_build)


async def test_a_built_curated_search_grounds_by_its_datasets_assay() -> None:
    ctx = _built(Criterion(id="c_pct", text="expressed", search_name=_PERCENTILE))

    await build_strategy(ctx)

    [grounded] = derive_ledger(ctx.deps.state, None).constraints.grounded
    assert (ctx.deps.state.domain.data_marks, grounded.status) == (
        DataMarks(searches={_PERCENTILE: "RNASeq"}),
        ConstraintStatus.GROUNDED,
    )


async def test_a_built_step_on_an_upload_grounds_by_the_uploads_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _uploads(site_id: str) -> list[OwnedUpload]:
        del site_id
        return [
            OwnedUpload(
                vdi_id="lhZ5ptRgo014J",
                name="pathfinder-uat-deseq",
                type_name="rnaseqrc",
            )
        ]

    monkeypatch.setattr(bound_uploads, "owned_uploads", _uploads)
    ctx = _built(
        Criterion(
            id="c_deseq",
            text="Genes differentially expressed in pathfinder-uat-deseq.",
            search_name="GenesByDESeqUserDataset",
            analysis=AnalysisBinding(
                dataset_id=UPLOAD_DATASET, method="DESeq", words="DESeq"
            ),
        )
    )

    await build_strategy(ctx)

    [grounded] = derive_ledger(ctx.deps.state, None).constraints.grounded
    [step_id] = ctx.deps.state.domain.data_marks.uploads
    assert (ctx.deps.state.domain.data_marks.uploads[step_id], grounded.status) == (
        "rnaseqrc",
        ConstraintStatus.GROUNDED,
    )
