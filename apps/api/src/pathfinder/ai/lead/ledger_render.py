"""The full detail of one ledger section, rendered for the Lead to read."""

from __future__ import annotations

from assistant_core.graph.tool_summary import count_noun

from pathfinder.ai.graph.state import VerificationDigest
from pathfinder.ai.lead.ledger_sections import (
    BuildSection,
    ConstraintSection,
    FrameSection,
    VerificationSection,
    render_structure,
)
from pathfinder.ai.tools.standalone.graph_helpers import counted_noun
from pathfinder.domain.caveats import Caveat, ControlsCaveat
from pathfinder.domain.evidence import NamedControlSet, VerificationReview
from pathfinder.domain.strategy.measurement_clauses import measurement_clauses
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    plain_value,
)

# The choices of one open slot the ledger prints.
_OPTION_WINDOW = 8


def render_constraints_full(section: ConstraintSection) -> str:
    if not section.grounded:
        return "## Constraints\n(none)"
    lines = [
        "## Constraints",
        f"blocking: {section.blocking}  unmet (user-explicit): {section.unmet_count}",
    ]
    for g in section.grounded:
        c = g.constraint
        realized = g.realized_value or "-"
        note = f" - {g.note}" if g.note else ""
        lines.append(
            f"- [{c.source}] {c.label} ({c.kind}): requested {c.requested_value!r} "
            f"-> {g.status} (realized {realized}){note}"
        )
    return "\n".join(lines)


def render_frame_full(section: FrameSection) -> str:
    spec = section.spec
    if spec is None:
        return "## Frame\n(no spec yet)"
    parts = [
        "## Frame (full)",
        f"- goal: {spec.goal}",
        f"- interpreted_goal: {spec.interpreted_goal}",
        f"- records: {counted_noun(spec.record_type)}s",
        f"- organism_scope: {spec.organism_scope or 'any'}",
        f"- title: {spec.title}",
        f"- ready_to_build: {spec.ready_to_build}",
        "",
        f"### Criteria ({len(spec.criteria)})",
    ]
    noun = counted_noun(spec.record_type)
    for crit in spec.criteria:
        parts.extend(_render_criterion(crit, noun))
    if spec.structure is not None:
        parts.append("\n### Structure")
        parts.append(render_structure(spec.structure.root, spec))
    if spec.open_slots:
        parts.append("\n### Open slots (user must answer)")
        parts.extend(
            f"- {s.criterion_id or '-'}.{s.param_name}: {_asked(s)}"
            for s in spec.open_slots
        )
    if spec.dropped:
        parts.append("\n### Dropped criteria")
        parts.extend(f"- {d.text} - {d.reason}" for d in spec.dropped)
    return "\n".join(parts)


def _asked(slot: OpenSlot) -> str:
    """The slot's question and the choices the question card offers for it."""
    if not slot.options:
        return slot.question
    shown = slot.options[:_OPTION_WINDOW]
    rest = len(slot.options) - len(shown)
    more = [f"{rest} more"] if rest else []
    return f"{slot.question}; options: {' | '.join([*shown, *more])}"


def _search_label(crit: Criterion) -> str:
    if crit.search_name:
        return crit.search_name
    if crit.pending_analysis:
        return f"(waiting for its analysis on {crit.needs_analysis_on})"
    return "(unbound)"


def _render_criterion(crit: Criterion, noun: str) -> list[str]:
    out = [
        (
            f"- `{crit.id}` [{crit.role}] {crit.text} -> "
            f"search={_search_label(crit)} (conf={crit.confidence:.2f})"
        ),
    ]
    if crit.analysis is not None:
        out.append(f"    selects: {crit.analysis.words}")
    reason = crit.step_rationale
    if reason is not None:
        out.append(f"    WHY {reason.line()}")
    out.extend(
        f"    {crit.display_name_of(name)} ({name}) = {plain_value(bound.value)} "
        f"({bound.source})"
        for name, bound in crit.resolved_params.items()
    )
    out.extend(
        f"    MEASURED {clause}" for clause in measurement_clauses(crit, noun=noun)
    )
    out.extend(f"    OPEN {s.param_name}: {_asked(s)}" for s in crit.open_params)
    out.extend(
        f"    CHOICES {a.param_name}: holds {a.bound}, "
        f"{count_noun(a.option_count, 'option')}"
        + (f", others {a.other_options}" if a.other_options else "")
        for a in crit.alternatives
    )
    return out


def render_build_full(section: BuildSection) -> str:
    if section.outcome is None:
        return "## Build\n(no build yet)"
    o = section.outcome
    parts = [
        "## Build (full)",
        f"- pushed: {len(o.pushed_step_ids)}",
        f"- failed: {len(o.failed_steps)}",
        f"- skipped: {len(o.skipped_step_ids)}",
        f"- zero_result_steps: {o.zero_step_ids}",
        f"- wdk_strategy_id: {o.wdk_strategy_id}",
    ]
    if o.organism_change is not None:
        parts.append(f"- records: {o.organism_change.line()}")
    if o.failed_steps:
        parts.append("\n### Failed steps")
        parts.extend(
            f"- {f.step_id} ({f.search_name}): {f.error}" for f in o.failed_steps
        )
    return "\n".join(parts)


def _verdict_line(digest: VerificationDigest) -> str:
    """Success, or a pass with the checks the site left pending, by step."""
    pending = digest.pending_checks
    if not digest.success or not pending:
        return f"- success: {digest.success}"
    return (
        f"- verdict: passed, {count_noun(len(pending), 'check')} pending: "
        f"{', '.join(pending)}"
    )


def render_verification_full(section: VerificationSection) -> str:
    if section.digest is None:
        return "## Verification\n(not run yet)"
    d = section.digest
    parts = [
        "## Verification (full)",
        _verdict_line(d),
        f"- prose: {d.prose}",
    ]
    if d.key_findings:
        parts.append("\n### Key findings")
        parts.extend(f"- {kf}" for kf in d.key_findings)
    if d.gaps:
        parts.append("\n### Gaps")
        parts.extend(f"- {gap.sentence}" for gap in d.gaps)
    if section.caveats:
        parts.append("\n### Caveats")
        parts.extend(_caveat_line(caveat) for caveat in section.caveats)
    parts.extend(_review_lines(d.review))
    return "\n".join(parts)


def _caveat_line(caveat: Caveat) -> str:
    """The caveat sentence, and the saved set a control test ran when it names one."""
    match caveat:
        case ControlsCaveat(control_set=NamedControlSet() as held):
            return f"- {caveat.sentence} (control set {held.name}, id {held.id})"
        case _:
            return f"- {caveat.sentence}"


def _review_lines(review: VerificationReview) -> list[str]:
    """Each requirement row, each column, each sampled gene and each source of
    the check."""
    lines: list[str] = []
    if review.requirements:
        lines.append("\n### Requirements")
        lines.extend(
            f"- [{row.shown_status}] {row.text} (message {row.turn}, {row.how}; answered "
            f"by {', '.join(row.answered_by) or 'nothing'}): {row.note}"
            for row in review.requirements
        )
    if review.column_fits:
        lines.append("\n### Columns")
        lines.extend(
            f"- [{fit.fits}] {fit.criterion_id}: {fit.sentence}"
            for fit in review.column_fits
        )
    if review.sampled_genes:
        lines.append("\n### Sampled genes")
        lines.extend(
            f"- {gene.gene_id}, {gene.product} ({gene.organism}): fits {gene.fits} "
            f"- {gene.why}"
            for gene in review.sampled_genes
        )
    if review.sources:
        lines.append("\n### Sources")
        lines.extend(
            f"- {cited.label} ({', '.join(cited.references())}): {cited.why}"
            for cited in review.sources
        )
    return lines
