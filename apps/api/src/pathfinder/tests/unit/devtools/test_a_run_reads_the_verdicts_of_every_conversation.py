from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from pathfinder.devtools import eval_runner
from pathfinder.devtools.chat import RunArgs
from pathfinder.devtools.gates import Gate
from pathfinder.domain.audit.verdicts import GeneModelVerdict
from pathfinder.evals.case import (
    CaseProvenance,
    EvalCase,
    ExpectedOutcome,
    GateEnd,
    GatePlan,
)
from pathfinder.evals.scoring import ObservedOutcome
from pathfinder.evals.verdict_scoring import ObservedVerdict
from pathfinder.services.audit.verdicts import VerdictView


class _Capture:
    def assistant_text(self) -> str:
        return "a reply"

    def turn_facts(self) -> None:
        return None

    def refused_tools(self) -> list[str]:
        return []


class _Observed:
    def __init__(self) -> None:
        self.driven: list[RunArgs] = []
        self.opened: list[UUID] = []
        self.users: list[UUID] = []


def _case() -> EvalCase:
    return EvalCase(
        name="an-audit-case",
        turns=["check this gene", "and this one", "now this one"],
        site_id="plasmodb",
        assistant_id="audit",
        rationale="pins a stored verdict",
        expected=ExpectedOutcome(builds_strategy=False, verdicts={"EXA_0001": "error"}),
        gates=GatePlan(policy="leave"),
        provenance=CaseProvenance(
            site="plasmodb",
            assistant="audit",
            origin="cataloged-failure",
            reference="a-design.md",
            added_at="2026-11-10",
        ),
        new_conversation_before=[2],
    )


def _install(monkeypatch: pytest.MonkeyPatch) -> _Observed:
    observed = _Observed()

    async def _drive(args: RunArgs) -> tuple[_Capture, Gate]:
        observed.driven.append(args)
        return _Capture(), Gate(kind="none")

    async def _step_ids(conversation_id: UUID) -> set[int]:
        del conversation_id
        return set()

    async def _reviewed(conversation_id: UUID) -> None:
        del conversation_id

    async def _observe(
        threads: eval_runner.CaseThreads,
        turns: eval_runner.TurnsShown,
        *,
        step_ids_unchanged: bool | None,
        ends_on: GateEnd | None,
        refused_tools: list[str],
    ) -> ObservedOutcome:
        del turns, step_ids_unchanged, ends_on, refused_tools
        observed.opened.extend(threads.conversation_ids)
        observed.users.append(threads.user_id)
        return ObservedOutcome(built_strategy=False)

    async def _forget(user_id: UUID) -> None:
        del user_id

    monkeypatch.setattr(eval_runner, "drive_run", _drive)
    monkeypatch.setattr(eval_runner, "persisted_wdk_step_ids", _step_ids)
    monkeypatch.setattr(eval_runner, "reviewed_checks", _reviewed)
    monkeypatch.setattr(eval_runner, "observe", _observe)
    monkeypatch.setattr(eval_runner, "forget_user", _forget)
    return observed


def _view(gene: str, hour: int) -> VerdictView:
    return VerdictView(
        id=hour,
        run_id=None,
        finding_id=None,
        origin="auditor",
        verdict=GeneModelVerdict(
            genes=(gene,),
            model_genome="Examplea alpha A",
            verdict="error",
            error_type="truncated_model",
            certainty="high",
            cause=f"the model of {gene} stops early",
            cites=("read_gene_model:" + gene,),
        ),
        review=None,
        created_at=datetime(2026, 11, 10, hour, tzinfo=UTC),
    )


async def test_the_run_observes_every_conversation_the_case_opened(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observed = _install(monkeypatch)

    await eval_runner.run_one_case(_case(), run_root=tmp_path)

    driven = [args.conversation_id for args in observed.driven]
    assert observed.opened == [driven[0], driven[2]]
    assert driven[0] == driven[1] != driven[2]
    assert observed.users == [observed.driven[0].user_id]


async def test_the_stored_verdicts_of_every_conversation_are_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, second, user = uuid4(), uuid4(), uuid4()
    stored = {first: [_view("EXA_0001", 9)], second: [_view("EXA_0002", 10)]}
    asked: list[tuple[UUID, UUID]] = []

    async def _verdicts(conversation_id: UUID, user_id: UUID) -> list[VerdictView]:
        asked.append((conversation_id, user_id))
        return stored[conversation_id]

    monkeypatch.setattr(eval_runner, "conversation_verdicts", _verdicts)

    verdicts = await eval_runner.stored_verdicts(
        eval_runner.CaseThreads(conversation_ids=[first, second], user_id=user)
    )

    assert asked == [(first, user), (second, user)]
    assert verdicts == {
        gene: ObservedVerdict(
            verdict="error",
            error_type="truncated_model",
            cause=f"the model of {gene} stops early",
        )
        for gene in ("EXA_0001", "EXA_0002")
    }
