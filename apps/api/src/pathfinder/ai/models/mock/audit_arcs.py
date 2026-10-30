from __future__ import annotations

import re
from uuid import UUID

from assistant_core.models.scripted import (
    current_turn,
    last_user_text,
    retry_prompt_parts,
    scripted_call,
)
from pydantic import TypeAdapter
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.audit.run_tools import START_TOOL
from pathfinder.ai.models.mock.calls import classify, lead_final
from pathfinder.ai.models.mock.directive import without_tokens
from pathfinder.ai.models.mock.reads import ToolAnswer, last_answer, last_return
from pathfinder.domain.audit.scope import AuditScope

AUDIT = "gene_model_audit"
PLAN = "plan_gene_model_audit"
LIST_RUNS = "list_audit_runs"
LIST_FINDINGS = "list_audit_findings"
READ_FINDINGS = "read_audit_findings"
INVESTIGATE = "investigate_gene_models"
START_REPLY = (
    "[mock] The planner's scope and cost are on the card below; the audit "
    "starts on your yes."
)
NOT_STARTED = "[mock] The audit was not started."
NO_RUN = "[mock] No audit run is stored for this researcher."
_GENOME = re.compile(r"gene models of (?P<genome>.+?)(?: against .*)?$")


class _Proposal(ToolAnswer):
    scope: AuditScope | None = None


class _PlanRead(ToolAnswer):
    answer: _Proposal


class _Run(ToolAnswer):
    id: UUID


class _RunsRead(ToolAnswer):
    answer: list[_Run]


class _Target(ToolAnswer):
    genes: list[str]


class _Finding(ToolAnswer):
    id: int
    target: _Target


class _Page(ToolAnswer):
    findings: list[_Finding]


class _PageRead(ToolAnswer):
    answer: _Page


class _Result(ToolAnswer):
    strain_cds_length: int


class _Confirmation(ToolAnswer):
    result: _Result


class _Payload(ToolAnswer):
    confirmation: _Confirmation


class _Evidence(ToolAnswer):
    payload: _Payload


class _Detail(ToolAnswer):
    finding: _Finding
    evidence: list[_Evidence]


class _DetailRead(ToolAnswer):
    answer: _Detail


_DETAILS = TypeAdapter(list[_DetailRead])


class _Investigation(ToolAnswer):
    answer: str


def _message(messages: list[ModelMessage]) -> str:
    return without_tokens(last_user_text(current_turn(messages)))


def _request(messages: list[ModelMessage]) -> dict[str, list[str]]:
    found = _GENOME.search(_message(messages))
    named = [] if found is None else found.group("genome").split(",")
    return {"genomes": [genome.strip() for genome in named]}


def _planned(messages: list[ModelMessage]) -> _PlanRead | None:
    return last_return(current_turn(messages), PLAN, _PlanRead)


def audit_start(messages: list[ModelMessage]) -> list[ToolCallPart]:
    request = _request(messages)
    head = [classify(AUDIT), scripted_call(PLAN, {"request": request})]
    planned = _planned(messages)
    if planned is None or planned.answer.scope is None:
        return [*head, lead_final(NOT_STARTED, "await_user")]
    scope = planned.answer.scope.model_dump(mode="json", by_alias=True)
    start = scripted_call(
        START_TOOL, {"reply": START_REPLY, "request": request, "scope": scope}
    )
    started = last_return(current_turn(messages), START_TOOL, ToolAnswer)
    if started is None:
        return [*head, start, lead_final(NOT_STARTED, "await_user")]
    said = "[mock] The audit is started; the facts show its run and its phase."
    return [*head, start, lead_final(said, "complete")]


def audit_plan(messages: list[ModelMessage]) -> list[ToolCallPart]:
    head = [classify(AUDIT), scripted_call(PLAN, {"request": _request(messages)})]
    planned = _planned(messages)
    if planned is None:
        return [*head, lead_final(NOT_STARTED, "await_user")]
    said = "[mock] The facts show the plan's cost and the genomes it leaves out."
    return [*head, lead_final(said, "await_user")]


def _finding_reads(
    messages: list[ModelMessage],
) -> tuple[list[ToolCallPart], _DetailRead | None]:
    turn = current_turn(messages)
    calls = [scripted_call(LIST_RUNS, {})]
    runs = last_return(turn, LIST_RUNS, _RunsRead)
    if runs is None or not runs.answer:
        return calls, None
    run_id = str(runs.answer[0].id)
    calls.append(scripted_call(LIST_FINDINGS, {"run_id": run_id, "query": {}}))
    page = last_return(turn, LIST_FINDINGS, _PageRead)
    if page is None or not page.answer.findings:
        return calls, None
    first = page.answer.findings[0].id
    calls.append(
        scripted_call(READ_FINDINGS, {"run_id": run_id, "finding_ids": [first]})
    )
    read = last_answer(turn, READ_FINDINGS)
    details = [] if read is None else _DETAILS.validate_python(read)
    return calls, details[0] if details else None


def _finding_answer(
    messages: list[ModelMessage], *, spelled: bool
) -> list[ToolCallPart]:
    calls, found = _finding_reads(messages)
    if found is None:
        return [classify(AUDIT), *calls, lead_final(NO_RUN, "await_user")]
    detail = found.answer
    gene = detail.finding.target.genes[0]
    if spelled and not retry_prompt_parts(current_turn(messages)):
        length = detail.evidence[0].payload.confirmation.result.strain_cds_length
        said = f"The model of [record:{gene}] holds a CDS of {length} bases."
    else:
        said = f"The finding above reads the model of [record:{gene}] as an error."
    return [classify(AUDIT), *calls, lead_final(said, "await_user")]


def audit_finding(messages: list[ModelMessage]) -> list[ToolCallPart]:
    return _finding_answer(messages, spelled=False)


def audit_finding_spelled(messages: list[ModelMessage]) -> list[ToolCallPart]:
    return _finding_answer(messages, spelled=True)


def audit_investigation(messages: list[ModelMessage]) -> list[ToolCallPart]:
    head = [
        classify(AUDIT),
        scripted_call(INVESTIGATE, {"question": _message(messages)}),
    ]
    found = last_return(current_turn(messages), INVESTIGATE, _Investigation)
    said = NOT_STARTED if found is None else found.answer
    return [*head, lead_final(said, "await_user")]
