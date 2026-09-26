"""The deterministic VERIFY: read the strategy, sample the root, read each
sampled gene's record, test the root against controls when the arc or the work
order names them, and review what the reads returned."""

from __future__ import annotations

import re

from assistant_core.models.scripted import (
    current_scope_id,
    scripted_call,
    terminal_call,
)
from pydantic import Field, JsonValue
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.arc import Script
from pathfinder.ai.models.mock.graph_pin import pinned_root_organism
from pathfinder.ai.models.mock.history import acted_tool_names, head_work_order
from pathfinder.ai.models.mock.lead_flow import FEEDBACK_PROSE, SUCCESS_PROSE
from pathfinder.ai.models.mock.message_words import turn_controls
from pathfinder.ai.models.mock.reads import (
    ToolAnswer,
    controls_sentence,
    gene_records,
    instructions_of,
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
_SAMPLE = "get_sample_records"
_RECORD = "read_gene_record"
# The mock reads two records, enough to fill both columns of the card.
_READS = 2
_ROOT = re.compile(
    r"The root is (?P<step>\S+), step (?P<wdk>\d+) on the site.*?"
    r"get_sample_records\(wdk_step_id=\d+, limit=(?P<limit>\d+)\)"
)
_EMPTY_ROOT = "It holds no gene to sample."
_CONTROLS_LINE = re.compile(r"^(positive|negative)_controls: (.*)$", re.MULTILINE)
_TRANSCRIPT_SUFFIX = re.compile(r"\.\d+$")


class _Record(ToolAnswer):
    id: str


class _Sample(ToolAnswer):
    records: list[_Record] = Field(default_factory=list)

    def gene_ids(self) -> list[str]:
        return [_TRANSCRIPT_SUFFIX.sub("", record.id) for record in self.records]


def review_call(messages: list[ModelMessage]) -> ToolCallPart | None:
    """The next sampling or reading call, or None once every read is in."""
    root = _ROOT.search(head_work_order(messages))
    if root is None:
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


def _controls(
    messages: list[ModelMessage], *, site_controls: bool
) -> tuple[list[str], list[str]] | None:
    """The controls the work order names, else the turn's when the arc tests them."""
    named = dict(_CONTROLS_LINE.findall(head_work_order(messages)))
    if named:
        return named["positive"].split(", "), named["negative"].split(", ")
    return turn_controls() if site_controls else None


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
    """The VERIFY script, testing the site's controls when ``site_controls``.

    The control test runs last, so its answer is still whole when the digest
    states its counts."""

    def script(messages: list[ModelMessage]) -> ToolCallPart:
        called = acted_tool_names(messages)
        if READ not in called:
            return scripted_call(READ, {"summary_only": False})
        reading = review_call(messages)
        if reading is not None:
            return reading
        controls = _controls(messages, site_controls=site_controls)
        if controls is not None and TEST not in called:
            positives, negatives = controls
            return scripted_call(
                TEST,
                {
                    "wdk_step_id": _tested_root(messages),
                    "positive_controls": positives,
                    "negative_controls": negatives,
                },
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
