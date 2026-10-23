"""The deterministic scripts the audit agents run on under the mock provider, driven by marker phrases."""

from __future__ import annotations

import re

from assistant_core.models.scripted import (
    RoleMarkers,
    ScriptedModel,
    ScriptedPart,
    current_turn,
    last_user_text,
    scripted_call,
    scripted_text,
    terminal_call,
    tool_return_parts,
)
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import FunctionModel

from pathfinder.domain.audit.verdicts import read_cite

INVESTIGATOR = "investigator"
PSEUDOGENE_CALL = "audit_pseudogene_call"
PSEUDOGENE_QUESTION = "pseudogene call"
_GENE = re.compile(r"\b[A-Za-z0-9]+_\d+\b")


class _Verdict(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    verdict: str


class _CheckRead(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    answer: _Verdict
    fact_id: str


def _pair(text: str) -> tuple[str, str] | None:
    match _GENE.findall(text):
        case [strain, reference, *_]:
            return strain, reference
        case _:
            return None


def _read_of(messages: list[ModelMessage], tool_name: str) -> _CheckRead | None:
    returned = [p for p in tool_return_parts(messages) if p.tool_name == tool_name]
    if not returned or returned[-1].outcome != "success":
        return None
    return _CheckRead.model_validate(returned[-1].content, from_attributes=True)


def _pseudogene_verdict(
    strain: str, reference: str, read: _CheckRead
) -> dict[str, object]:
    intact = read.answer.verdict == "INTACT"
    return {
        "genes": [strain],
        "modelGenome": f"the genome of {strain}",
        "verdict": "error" if intact else "undecided",
        "errorType": "intact_gene_called_pseudogene" if intact else None,
        "certainty": "high" if intact else None,
        "cause": f"The check reads {strain} against {reference} as {read.answer.verdict}.",
        "cites": [read_cite(PSEUDOGENE_CALL, strain, reference)],
    }


def _investigator_script(messages: list[ModelMessage]) -> ScriptedPart:
    turn = current_turn(messages)
    text = last_user_text(turn)
    pair = _pair(text) if PSEUDOGENE_QUESTION in text.lower() else None
    if pair is None:
        return terminal_call(
            {"answer": "No check answers this question.", "verdicts": []}
        )
    strain, reference = pair
    read = _read_of(turn, PSEUDOGENE_CALL)
    if read is None:
        return scripted_call(
            PSEUDOGENE_CALL, {"strain_gene": strain, "reference_gene": reference}
        )
    return terminal_call(
        {
            "answer": (
                f"The check reads the model of [record:{strain}] as "
                f"[stat:{read.fact_id}.verdict]."
            ),
            "verdicts": [_pseudogene_verdict(strain, reference, read)],
        }
    )


def _title_script(messages: list[ModelMessage]) -> ScriptedPart:
    lines = last_user_text(messages).splitlines()
    return scripted_text(lines[-1] if lines else "")


_SCRIPT = ScriptedModel(
    roles=(RoleMarkers(role=INVESTIGATOR, markers=frozenset({PSEUDOGENE_CALL})),),
    scripts={INVESTIGATOR: _investigator_script},
    unknown=_title_script,
)


def build_audit_mock() -> FunctionModel:
    return _SCRIPT.as_function_model()
