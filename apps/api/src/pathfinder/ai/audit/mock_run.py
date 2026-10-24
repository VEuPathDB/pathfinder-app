from __future__ import annotations

import re

from assistant_core.models.scripted import (
    ScriptedPart,
    scripted_call,
    terminal_call,
    tool_return_parts,
)
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, TypeAdapter
from pydantic_ai.messages import ModelMessage

from pathfinder.domain.audit.verdicts import finding_cite

LIST_FINDINGS_TOOL = "list_audit_findings"
READ_FINDINGS_TOOL = "read_audit_findings"
RECORD_TOOL = "record_gene_model_verdicts"
FINDINGS_PER_MOCK_CALL = 25
JUDGED_EVERY_FINDING = (
    "I judged every finding of the run and stored a verdict for each."
)
JUDGE_REQUEST = re.compile(
    r"judge every finding of audit run (?P<run>[0-9a-f-]{36})", re.IGNORECASE
)


class _Target(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    genes: list[str]


class _Finding(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    id: int
    genome: str
    target: _Target
    error_type: str | None = None
    certainty: str | None = None


class _Page(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    findings: list[_Finding]


class _PageRead(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    answer: _Page


class _Detail(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    finding: _Finding


class _DetailRead(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    answer: _Detail


_DETAILS: TypeAdapter[list[_DetailRead]] = TypeAdapter(list[_DetailRead])


def _verdict(finding: _Finding) -> dict[str, object]:
    named = finding.error_type is not None
    return {
        "genes": finding.target.genes,
        "modelGenome": finding.genome,
        "verdict": "error" if named else "no_error",
        "errorType": finding.error_type,
        "certainty": finding.certainty,
        "cause": "The stored check of the finding settles the model.",
        "cites": [finding_cite(finding.id)],
    }


def judge_the_run(turn: list[ModelMessage], run_id: str) -> ScriptedPart:
    returned = tool_return_parts(turn)
    listed = [p for p in returned if p.tool_name == LIST_FINDINGS_TOOL]
    if not listed:
        return scripted_call(
            LIST_FINDINGS_TOOL, {"run_id": run_id, "query": {"limit": 200}}
        )
    page = _PageRead.model_validate(listed[-1].content, from_attributes=True)
    reads = [p for p in returned if p.tool_name == READ_FINDINGS_TOOL]
    records = [p for p in returned if p.tool_name == RECORD_TOOL]
    if len(reads) > len(records):
        details = _DETAILS.validate_python(reads[-1].content, from_attributes=True)
        verdicts = [_verdict(read.answer.finding) for read in details]
        return scripted_call(RECORD_TOOL, {"verdicts": verdicts})
    start = len(reads) * FINDINGS_PER_MOCK_CALL
    batch = page.answer.findings[start : start + FINDINGS_PER_MOCK_CALL]
    if not batch:
        return terminal_call({"prose": JUDGED_EVERY_FINDING})
    ids = [finding.id for finding in batch]
    return scripted_call(READ_FINDINGS_TOOL, {"run_id": run_id, "finding_ids": ids})
