"""The deterministic VERIFY: read the strategy, read each search step's columns,
sample the root and read each sampled gene's record only when a step shows no
column, test the root against a saved control set when the work order names
one or the arc tests the listed sets, and review what the reads returned."""

from __future__ import annotations

import re

from assistant_core.models.scripted import (
    called_tool_parts,
    current_scope_id,
    scripted_call,
    terminal_call,
)
from pydantic import Field, JsonValue, TypeAdapter
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.arc import Script
from pathfinder.ai.models.mock.graph_pin import pinned_root_organism
from pathfinder.ai.models.mock.history import acted_tool_names, head_work_order
from pathfinder.ai.models.mock.lead_flow import FEEDBACK_PROSE, SUCCESS_PROSE
from pathfinder.ai.models.mock.reads import (
    ToolAnswer,
    controls_sentence,
    gene_records,
    instructions_of,
    last_answer,
    returns_of,
    root_wdk_step_id,
)
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.domain.evidence import RequirementCheck, SampledGene, VerificationReview
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    message_states_constraint,
)

READ = "get_strategy"
TEST = "run_control_tests_on_step"
LIST = "list_control_sets"
_COLUMNS = "read_step_columns"
_SAMPLE = "get_sample_records"
_RECORD = "read_gene_record"
# The mock reads two records, enough to fill both columns of the card.
_READS = 2
_ROOT = re.compile(
    r"The root is (?P<step>\S+), step (?P<wdk>\d+) on the site.*?"
    r"get_sample_records\(wdk_step_id=\d+, limit=(?P<limit>\d+)\)"
)
_COLUMN_STEP = re.compile(r"read_step_columns\(wdk_step_id=(?P<wdk>\d+)\)")
_EMPTY_ROOT = "It holds no gene to sample."
_ORDERED_SET = re.compile(r"\bcontrol_set_id (?P<id>[^\s,]+)")
_TRANSCRIPT_SUFFIX = re.compile(r"\.\d+$")


class _Record(ToolAnswer):
    id: str


class _Columns(ToolAnswer):
    # Set when the step's search shows no column for its bound values.
    note: str = ""


class _Listed(ToolAnswer):
    control_set_id: str


_LISTING = TypeAdapter(list[_Listed])


class _Sample(ToolAnswer):
    records: list[_Record] = Field(default_factory=list)

    def gene_ids(self) -> list[str]:
        return [_TRANSCRIPT_SUFFIX.sub("", record.id) for record in self.records]


def _column_call(messages: list[ModelMessage]) -> ToolCallPart | None:
    """The next search step whose columns the work order names and no call read."""
    listed = [int(m["wdk"]) for m in _COLUMN_STEP.finditer(head_work_order(messages))]
    read = {
        part.args_as_dict()["wdk_step_id"]
        for part in called_tool_parts(messages)
        if part.tool_name == _COLUMNS
    }
    unread = [wdk for wdk in listed if wdk not in read]
    return scripted_call(_COLUMNS, {"wdk_step_id": unread[0]}) if unread else None


def _no_column(messages: list[ModelMessage]) -> bool:
    """Whether a step shows no column, or the work order names no search step."""
    listed = _COLUMN_STEP.search(head_work_order(messages)) is not None
    answers = returns_of(messages, _COLUMNS, _Columns)
    return not listed or any(answer.note for answer in answers)


def review_call(messages: list[ModelMessage]) -> ToolCallPart | None:
    """The next column, sampling or reading call, or None once every read is in."""
    columns = _column_call(messages)
    if columns is not None:
        return columns
    root = _ROOT.search(head_work_order(messages))
    if root is None or not _no_column(messages):
        return None
    if _SAMPLE not in acted_tool_names(messages):
        limit = min(int(root["limit"]), _READS)
        return scripted_call(_SAMPLE, {"wdk_step_id": int(root["wdk"]), "limit": limit})
    read = {record.gene_id for record in gene_records(messages)}
    sampled = [g for s in returns_of(messages, _SAMPLE, _Sample) for g in s.gene_ids()]
    unread = [gene_id for gene_id in sampled[:_READS] if gene_id not in read]
    return scripted_call(_RECORD, {"gene_id": unread[0]}) if unread else None


def review(messages: list[ModelMessage], organism: str) -> dict[str, JsonValue]:
    """The review of the genes this run read, against the organism searched."""
    root = _ROOT.search(head_work_order(messages))
    if root is None:
        return {}
    searched = Constraint(
        kind=ConstraintKind.ORGANISM, requested_value=organism, label="organism"
    )
    records = gene_records(messages)
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


def _ordered_set(messages: list[ModelMessage]) -> str | None:
    """The saved control set the work order names, or None."""
    ordered = _ORDERED_SET.search(head_work_order(messages))
    return None if ordered is None else ordered["id"]


def _listed_set(messages: list[ModelMessage]) -> str | None:
    """The newest saved control set the listing names, or None."""
    listed = last_answer(messages, LIST)
    if listed is None:
        return None
    sets = _LISTING.validate_python(listed)
    return sets[0].control_set_id if sets else None


def verification_delta(
    *, success: bool, prose: str, review: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    return {
        "digest": {
            "disposition": "done" if success else "awaiting_user",
            "prose": prose,
            "reason": "mock verification",
            "success": success,
            "review": review,
        },
    }


def _root_organism(messages: list[ModelMessage]) -> str:
    """The organism the pinned root holds, named in full as a read record names
    it when the pin cuts it, else the site's organism."""
    pinned = pinned_root_organism(instructions_of(messages))
    if pinned is None:
        return SiteValues.for_site(current_scope_id.get()).organism
    named = (
        r.organism for r in gene_records(messages) if r.organism.startswith(pinned)
    )
    return next(named, pinned)


def _tested_root(messages: list[ModelMessage]) -> int | None:
    """The root the work order samples, else the one the strategy read names."""
    root = _ROOT.search(head_work_order(messages))
    return root_wdk_step_id(messages) if root is None else int(root["wdk"])


def verification(*, site_controls: bool) -> Script:
    """The VERIFY script, testing a control set saved on the site when
    ``site_controls``, or the set the work order names.

    The control test runs last, so its answer is still whole when the digest
    states its counts."""

    def script(messages: list[ModelMessage]) -> ToolCallPart:
        called = acted_tool_names(messages)
        if READ not in called:
            return scripted_call(READ, {"summary_only": False})
        reading = review_call(messages)
        if reading is not None:
            return reading
        ordered = _ordered_set(messages)
        if ordered is None and site_controls and LIST not in called:
            return scripted_call(LIST, {})
        control_set = ordered or _listed_set(messages)
        if control_set is not None and TEST not in called:
            return scripted_call(
                TEST,
                {"wdk_step_id": _tested_root(messages), "control_set_id": control_set},
            )
        success = _EMPTY_ROOT not in head_work_order(messages)
        organism = _root_organism(messages)
        found = SUCCESS_PROSE if success else FEEDBACK_PROSE
        return terminal_call(
            verification_delta(
                success=success,
                prose=controls_sentence(messages) or found,
                review=review(messages, organism),
            )
        )

    return script
