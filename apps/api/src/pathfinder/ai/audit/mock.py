"""The deterministic scripts the audit agents run on under the mock provider, driven by marker phrases."""

from __future__ import annotations

import re
from uuid import UUID

from assistant_core.models.scripted import (
    RoleMarkers,
    ScriptedModel,
    ScriptedPart,
    current_turn,
    has_any,
    last_user_text,
    retry_prompt_parts,
    scripted_call,
    scripted_text,
    terminal_call,
    tool_names,
    tool_return_parts,
    user_texts,
)
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.profiles import ModelProfile

from pathfinder.ai.audit.mock_investigation import (
    INVESTIGATOR,
    PSEUDOGENE_CALL,
    PSEUDOGENE_QUESTION,
    check_read,
    gene_pair,
    investigator_script,
    last_tool_return,
    pseudogene_verdict,
)
from pathfinder.ai.audit.mock_run import JUDGE_REQUEST, judge_the_run
from pathfinder.ai.audit.run_tools import START_TOOL
from pathfinder.ai.lead.retrieval_toolset import ResearchAnswer
from pathfinder.domain.audit.scope import AuditScope
from pathfinder.domain.audit.verdicts import (
    MAX_CITES,
    MAX_HEADLINES,
    finding_cite,
)

AUDITOR = "auditor"
PLAN_TOOL = "plan_gene_model_audit"
LIST_RUNS_TOOL = "list_audit_runs"
READ_RUN_TOOL = "read_audit_run"
VERDICT_TOOL = "record_gene_model_verdicts"
RATE_TOOL = "rate_with_interval"
PROGRESS_QUESTIONS = ("how is the audit", "how far is the audit")
CHECK_FOREVER = "check every gene"
SPELL_OUT = "spell out"
LITERATURE_TOOL = "research_literature_search"
MOCK_REVIEWER_MODEL_ID = "mock:reviewer"
MOCK_SYNTHESIS_MODEL_ID = "mock:synthesis"
AUDITOR_GREETING = "I plan, start and read audits of the gene models on this site."
_AUDIT_REQUEST = re.compile(
    r"audit the gene models of (?P<genome>[^.?!]+)", re.IGNORECASE
)


class _Read(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    fact_id: str


def _judged(
    turn: list[ModelMessage], strain: str, reference: str, *, spelled: bool
) -> ScriptedPart:
    read = check_read(turn, PSEUDOGENE_CALL)
    if read is None:
        return scripted_call(
            PSEUDOGENE_CALL, {"strain_gene": strain, "reference_gene": reference}
        )
    if last_tool_return(turn, VERDICT_TOOL) is None:
        return scripted_call(
            VERDICT_TOOL, {"verdicts": [pseudogene_verdict(strain, reference, read)]}
        )
    written = spelled and not retry_prompt_parts(turn)
    length = (
        str(read.answer.strain_cds_length)
        if written
        else f"[stat:{read.fact_id}.strainCdsLength]"
    )
    return terminal_call(
        {"prose": f"The model of [record:{strain}] holds a CDS of {length} bases."}
    )


class _Proposal(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    scope: AuditScope | None


class _PlanRead(_Read):
    answer: _Proposal


def _audit(turn: list[ModelMessage], genome: str) -> ScriptedPart:
    request = {"genomes": [genome]}
    planned = last_tool_return(turn, PLAN_TOOL)
    if planned is None:
        return scripted_call(PLAN_TOOL, {"request": request})
    scope = _PlanRead.model_validate(planned.content, from_attributes=True).answer.scope
    if scope is None:
        return terminal_call({"prose": "The planner starts no audit for this request."})
    started = last_tool_return(turn, START_TOOL)
    if started is None:
        dumped = scope.model_dump(mode="json", by_alias=True)
        return scripted_call(START_TOOL, {"request": request, "scope": dumped})
    if started.outcome != "success":
        return terminal_call({"prose": "The audit was not started, as you answered."})
    fact = _Read.model_validate(started.content, from_attributes=True).fact_id
    return terminal_call(
        {"prose": f"Audit run [stat:{fact}.runId] is [stat:{fact}.phase]."}
    )


class _RunId(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    id: UUID


class _RunsRead(_Read):
    answer: list[_RunId]


class _Rate(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    bounds: object | None


class _RunView(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    rates: list[_Rate]


class _RunRead(_Read):
    answer: _RunView


def _progress_reply(read: _RunRead) -> str:
    fact = read.fact_id
    said = (
        f"Audit run [stat:{fact}.run.id] is [stat:{fact}.run.status]. Its "
        f"confirmation stage has checked [stat:{fact}.stages.stages.2.done] of "
        f"[stat:{fact}.stages.stages.2.total] candidates."
    )
    rates = read.answer.rates
    if rates and rates[0].bounds is not None:
        said += f" The first rate is at least [stat:{fact}.rates.0.bounds.low]."
    return said


def _progress(turn: list[ModelMessage]) -> ScriptedPart:
    listed = last_tool_return(turn, LIST_RUNS_TOOL)
    if listed is None:
        return scripted_call(LIST_RUNS_TOOL, {})
    runs = _RunsRead.model_validate(listed.content, from_attributes=True).answer
    if not runs:
        return terminal_call({"prose": "No audit run is stored for this researcher."})
    read = last_tool_return(turn, READ_RUN_TOOL)
    if read is None:
        return scripted_call(READ_RUN_TOOL, {"run_id": str(runs[0].id)})
    view = _RunRead.model_validate(read.content, from_attributes=True)
    return terminal_call({"prose": _progress_reply(view)})


def _forever(turn: list[ModelMessage]) -> ScriptedPart:
    made = [p for p in tool_return_parts(turn) if p.tool_name == RATE_TOOL]
    args = {"confirmed": 1, "checked": len(made) + 2, "unresolved": 0}
    return scripted_call(RATE_TOOL, args)


def _auditor_script(messages: list[ModelMessage]) -> ScriptedPart:
    turn = current_turn(messages)
    text = last_user_text(turn)
    lowered = text.lower()
    if CHECK_FOREVER in lowered:
        return _forever(turn)
    if has_any(lowered, PROGRESS_QUESTIONS):
        return _progress(turn)
    asked = _AUDIT_REQUEST.search(text)
    if asked is not None:
        return _audit(turn, asked.group("genome").strip())
    judged = JUDGE_REQUEST.search(text)
    if judged is not None:
        return judge_the_run(turn, judged.group("run"))
    pair = gene_pair(text) if PSEUDOGENE_QUESTION in lowered else None
    if pair is not None:
        return _judged(turn, *pair, spelled=SPELL_OUT in lowered)
    return terminal_call({"prose": AUDITOR_GREETING})


def _title_script(messages: list[ModelMessage]) -> ScriptedPart:
    lines = last_user_text(messages).splitlines()
    return scripted_text(lines[-1] if lines else "")


_SCRIPT = ScriptedModel(
    roles=(
        RoleMarkers(role=AUDITOR, markers=frozenset({PLAN_TOOL})),
        RoleMarkers(role=INVESTIGATOR, markers=frozenset({PSEUDOGENE_CALL})),
    ),
    scripts={AUDITOR: _auditor_script, INVESTIGATOR: investigator_script},
    unknown=_title_script,
)


def build_audit_mock() -> FunctionModel:
    return _SCRIPT.as_function_model()


class _ReviewTarget(CamelModel):
    model_config = ConfigDict(extra="ignore")

    genes: list[str]


class _ReviewedFinding(CamelModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    genome: str
    target: _ReviewTarget
    error_type: str | None = None
    certainty: str | None = None


class _ReviewPrompt(CamelModel):
    model_config = ConfigDict(extra="ignore")

    finding: _ReviewedFinding


def _literature(turn: list[ModelMessage]) -> list[str] | None:
    found = last_tool_return(turn, LITERATURE_TOOL)
    if found is None:
        return None
    return ResearchAnswer.model_validate(found.content).references()[:MAX_CITES]


def _known(found: list[str] | None) -> str:
    if found is None:
        return "not_searched"
    return "known" if found else "not_found"


def _review_args(
    finding: _ReviewedFinding, found: list[str] | None
) -> dict[str, object]:
    named = finding.error_type is not None
    genes = ", ".join(finding.target.genes)
    return {
        "verdict": {
            "genes": finding.target.genes,
            "modelGenome": finding.genome,
            "verdict": "error" if named else "undecided",
            "errorType": finding.error_type,
            "certainty": finding.certainty,
            "cause": f"The stored checks of {genes} confirm the finding.",
            "cites": [finding_cite(finding.id)],
        },
        "alreadyKnown": _known(found),
        "knownFrom": found or [],
        "cardText": f"The model of {genes} disagrees with the stored evidence.",
    }


def _review_part(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    turn = current_turn(messages)
    finding = _ReviewPrompt.model_validate_json(user_texts(turn)[0]).finding
    found = _literature(turn)
    if found is None and LITERATURE_TOOL in tool_names(info):
        query = f"{' '.join(finding.target.genes)} gene model"
        return ModelResponse(parts=[scripted_call(LITERATURE_TOOL, {"query": query})])
    return ModelResponse(parts=[terminal_call(_review_args(finding, found))])


def build_review_mock() -> FunctionModel:
    return FunctionModel(
        _review_part,
        model_name=MOCK_REVIEWER_MODEL_ID,
        profile=ModelProfile(supports_inline_system_prompts=True),
    )


class _KeptVerdict(CamelModel):
    model_config = ConfigDict(extra="ignore")

    error_type: str
    cause: str


class _Kept(CamelModel):
    model_config = ConfigDict(extra="ignore")

    finding_id: int
    verdict: _KeptVerdict
    impact: float | None


class _SynthesisPrompt(CamelModel):
    model_config = ConfigDict(extra="ignore")

    kept_findings: list[_Kept]
    counts_fact: str


def _impact_rank(kept: _Kept) -> float:
    return -1.0 if kept.impact is None else kept.impact


def _synthesis_section(kept: list[_Kept]) -> dict[str, object]:
    return {
        "errorType": kept[0].verdict.error_type,
        "cause": kept[0].verdict.cause,
        "confirmedBy": "The stored evidence of the kept findings confirms it.",
        "findingIds": [k.finding_id for k in kept],
    }


def _synthesis_part(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    del info
    prompt = _SynthesisPrompt.model_validate_json(user_texts(current_turn(messages))[0])
    ranked = sorted(prompt.kept_findings, key=_impact_rank, reverse=True)
    grouped: dict[str, list[_Kept]] = {}
    for kept in ranked:
        grouped.setdefault(kept.verdict.error_type, []).append(kept)
    draft = {
        "sections": [_synthesis_section(group) for group in grouped.values()],
        "headline": [k.finding_id for k in ranked[:MAX_HEADLINES]],
        "summary": (
            f"The review kept [stat:{prompt.counts_fact}.kept] findings as errors and "
            f"rejected [stat:{prompt.counts_fact}.rejected]."
        ),
    }
    return ModelResponse(parts=[terminal_call(draft)])


def build_synthesis_mock() -> FunctionModel:
    return FunctionModel(
        _synthesis_part,
        model_name=MOCK_SYNTHESIS_MODEL_ID,
        profile=ModelProfile(supports_inline_system_prompts=True),
    )
