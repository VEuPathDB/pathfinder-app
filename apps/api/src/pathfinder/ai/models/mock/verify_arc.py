"""The review arc of the deterministic VERIFY: sample the root, read each sampled
gene's record, and review what the tool answers of the run returned."""

from __future__ import annotations

import re

from assistant_core.models.scripted import scripted_call, tool_return_parts
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field, JsonValue, ValidationError
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.history import acted_tool_names, head_work_order
from pathfinder.domain.evidence import RequirementCheck, SampledGene, VerificationReview
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    message_states_constraint,
)

_SAMPLE = "get_sample_records"
_READ = "read_gene_record"
# The mock reads two records, enough to fill both columns of the card.
_READS = 2
_ROOT = re.compile(
    r"The root is (?P<step>\S+), step (?P<wdk>\d+) on the site.*?"
    r"get_sample_records\(wdk_step_id=\d+, limit=(?P<limit>\d+)\)"
)
_TRANSCRIPT_SUFFIX = re.compile(r"\.\d+$")


class _SampledRecord(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    id: str


class _Sample(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    records: list[_SampledRecord] = Field(default_factory=list)

    def gene_ids(self) -> list[str]:
        return [_TRANSCRIPT_SUFFIX.sub("", record.id) for record in self.records]


class _Record(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    gene_id: str
    organism: str = ""
    product: str = ""


def _answers[T: CamelModel](
    messages: list[ModelMessage], tool: str, shape: type[T]
) -> list[T]:
    parsed: list[T] = []
    for part in tool_return_parts(messages):
        if part.tool_name != tool:
            continue
        try:
            parsed.append(shape.model_validate(part.content))
        except ValidationError:
            continue
    return parsed


def review_call(messages: list[ModelMessage]) -> ToolCallPart | None:
    """The next sampling or reading call, or None once every read is in."""
    root = _ROOT.search(head_work_order(messages))
    if root is None:
        return None
    if _SAMPLE not in acted_tool_names(messages):
        limit = min(int(root["limit"]), _READS)
        return scripted_call(_SAMPLE, {"wdk_step_id": int(root["wdk"]), "limit": limit})
    read = {record.gene_id for record in _answers(messages, _READ, _Record)}
    sampled = [g for s in _answers(messages, _SAMPLE, _Sample) for g in s.gene_ids()]
    unread = [gene_id for gene_id in sampled[:_READS] if gene_id not in read]
    return scripted_call(_READ, {"gene_id": unread[0]}) if unread else None


def review(messages: list[ModelMessage], organism: str) -> dict[str, JsonValue]:
    """The review of the genes this run read, against the organism searched."""
    root = _ROOT.search(head_work_order(messages))
    if root is None:
        return {}
    searched = Constraint(
        kind=ConstraintKind.ORGANISM, requested_value=organism, label="organism"
    )
    records = _answers(messages, _READ, _Record)
    fits = [message_states_constraint(r.organism, searched) for r in records]
    return VerificationReview(
        requirements=[
            RequirementCheck(
                text=organism,
                turn=1,
                answered_by=[root["step"]],
                how="parameter",
                status="met",
                note=f"organism = {organism}",
            )
        ],
        sampled_genes=[
            SampledGene(
                gene_id=record.gene_id,
                product=record.product,
                organism=record.organism,
                fits="yes" if fit else "no",
                why=(
                    f"the record names {organism}"
                    if fit
                    else f"the record names another organism than {organism}"
                ),
            )
            for record, fit in zip(records, fits, strict=True)
        ],
    ).model_dump(by_alias=True, mode="json")


__all__ = ["review", "review_call"]
