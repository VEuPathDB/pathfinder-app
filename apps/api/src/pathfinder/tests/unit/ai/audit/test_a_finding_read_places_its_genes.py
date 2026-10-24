from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic_ai import ModelRetry

from pathfinder.ai.audit import run_tools, verdict_tool
from pathfinder.ai.audit.run_tools import read_audit_findings_tool
from pathfinder.ai.audit.verdict_tool import (
    record_gene_model_verdicts,
    unheld_genomes_message,
)
from pathfinder.domain.audit.scope import GenePairTarget
from pathfinder.domain.audit.verdicts import GeneModelVerdict
from pathfinder.services.audit.finding_views import FindingDetail, FindingView
from pathfinder.services.audit.verdicts import AuditCaller
from pathfinder.tests._support.audit_check_runs import (
    REFERENCE,
    STRAIN,
    check_deps,
)
from pathfinder.tests._support.run_context import run_context_for

_JUDGED = "Examplea alpha A"
_SCREENED = "Examplea alpha S"
_PAIRED = "Examplea alpha R"


def _detail() -> FindingDetail:
    return FindingDetail(
        site_id="plasmodb",
        finding=FindingView(
            id=7,
            genome=_JUDGED,
            screened_genome=_SCREENED,
            paired_genome=_PAIRED,
            target=GenePairTarget(check="strain_model", genes=(STRAIN, REFERENCE)),
            sampled=True,
            status="confirmed",
            error_type=None,
            certainty=None,
            judged=True,
            impact=None,
            weighing=None,
            requests=4,
            attempts=1,
            stopped=0,
            message=None,
            reviewed=False,
            verdict=None,
            from_target=True,
            review_line=None,
            genes=[],
        ),
        evidence=[],
        facts=[],
        review=None,
        review_text=None,
        genes=[],
        models=None,
    )


@pytest.fixture(autouse=True)
def stored(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    kept: list[str] = []

    async def read(caller: AuditCaller, run_id: UUID, finding_id: int) -> FindingDetail:
        del caller, run_id
        assert finding_id == 7
        return _detail()

    async def store(*, verdict: GeneModelVerdict, **_: object) -> int:
        kept.append(verdict.model_genome)
        return len(kept)

    monkeypatch.setattr(run_tools, "read_audit_finding", read)
    monkeypatch.setattr(verdict_tool, "record_verdict", store)
    return kept


def _review(genome: str) -> GeneModelVerdict:
    return GeneModelVerdict(
        genes=(STRAIN, REFERENCE),
        model_genome=genome,
        verdict="no_error",
        cause="The strain model holds.",
        cites=("finding:7",),
    )


@pytest.mark.parametrize("genome", [_SCREENED, _PAIRED, _JUDGED])
async def test_a_review_names_the_screened_or_paired_genome_of_its_finding(
    stored: list[str], genome: str
) -> None:
    deps = check_deps()
    await read_audit_findings_tool(run_context_for(deps), uuid4(), [7])

    await record_gene_model_verdicts(run_context_for(deps), [_review(genome)])

    assert stored == [genome]


async def test_a_review_naming_a_genome_its_finding_does_not_name_is_refused(
    stored: list[str],
) -> None:
    deps = check_deps()
    await read_audit_findings_tool(run_context_for(deps), uuid4(), [7])

    with pytest.raises(ModelRetry) as refused:
        await record_gene_model_verdicts(
            run_context_for(deps), [_review("Otherus gamma G")]
        )

    assert str(refused.value) == unheld_genomes_message(
        [
            (
                "Otherus gamma G is not the genome of EXA_0001, EXR_0001, which the "
                f"reads place in {_JUDGED}, {_PAIRED}, {_SCREENED}"
            )
        ]
    )
    assert stored == []
