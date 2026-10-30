"""The investigator's deterministic script under the mock provider, read from the gene pair its question names."""

from __future__ import annotations

import re

from assistant_core.models.scripted import (
    ScriptedPart,
    current_turn,
    last_user_text,
    scripted_call,
    terminal_call,
    tool_return_parts,
)
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from pydantic_ai.messages import ModelMessage, ToolReturnPart

from pathfinder.domain.audit.verdicts import read_cite

INVESTIGATOR = "investigator"
PSEUDOGENE_CALL = "audit_pseudogene_call"
PSEUDOGENE_QUESTION = "pseudogene call"
_GENE = re.compile(r"\b[A-Za-z0-9]+_\d+\b")


class _Verdict(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    verdict: str
    strain_cds_length: int | None = None


class CheckRead(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    answer: _Verdict
    genomes: dict[str, str]


def gene_pair(text: str) -> tuple[str, str] | None:
    match _GENE.findall(text):
        case [strain, reference, *_]:
            return strain, reference
        case _:
            return None


def last_tool_return(
    messages: list[ModelMessage], tool_name: str
) -> ToolReturnPart | None:
    found = [p for p in tool_return_parts(messages) if p.tool_name == tool_name]
    return found[-1] if found else None


def check_read(messages: list[ModelMessage], tool_name: str) -> CheckRead | None:
    found = last_tool_return(messages, tool_name)
    if found is None or found.outcome != "success":
        return None
    return CheckRead.model_validate(found.content, from_attributes=True)


def pseudogene_verdict(
    strain: str, reference: str, read: CheckRead
) -> dict[str, object]:
    intact = read.answer.verdict == "INTACT"
    return {
        "genes": [strain],
        "modelGenome": read.genomes[strain],
        "verdict": "error" if intact else "undecided",
        "errorType": "intact_gene_called_pseudogene" if intact else None,
        "certainty": "high" if intact else None,
        "cause": f"The check reads {strain} against {reference} as {read.answer.verdict}.",
        "cites": [read_cite(PSEUDOGENE_CALL, strain, reference)],
    }


def investigator_script(messages: list[ModelMessage]) -> ScriptedPart:
    turn = current_turn(messages)
    text = last_user_text(turn)
    pair = gene_pair(text) if PSEUDOGENE_QUESTION in text.lower() else None
    if pair is None:
        return terminal_call(
            {"answer": "No check answers this question.", "verdicts": []}
        )
    strain, reference = pair
    read = check_read(turn, PSEUDOGENE_CALL)
    if read is None:
        return scripted_call(
            PSEUDOGENE_CALL, {"strain_gene": strain, "reference_gene": reference}
        )
    return terminal_call(
        {
            "answer": (
                f"The check reads the model of [record:{strain}] as "
                f"{read.answer.verdict.lower()}."
            ),
            "verdicts": [pseudogene_verdict(strain, reference, read)],
        }
    )
