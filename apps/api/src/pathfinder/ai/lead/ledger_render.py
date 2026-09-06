"""The full detail of one ledger section, rendered for the Lead to read."""

from __future__ import annotations

from veupathdb.domain.strategy.operational_spec import Criterion

from pathfinder.ai.lead.ledger_sections import (
    BuildSection,
    ConstraintSection,
    FrameSection,
    VerificationSection,
    render_structure,
)


def render_constraints_full(section: ConstraintSection) -> str:
    if not section.grounded:
        return "## Constraints\n(none)"
    lines = [
        "## Constraints",
        f"blocking: {section.blocking}  unmet (user-explicit): {section.unmet_count}",
    ]
    for g in section.grounded:
        c = g.constraint
        realized = g.realized_value or "—"
        note = f" — {g.note}" if g.note else ""
        lines.append(
            f"- [{c.source}] {c.label} ({c.kind}): requested {c.requested_value!r} "
            f"→ {g.status} (realized {realized}){note}"
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
        f"- record_type: {spec.record_type}",
        f"- organism_scope: {spec.organism_scope or 'any'}",
        f"- title: {spec.title}",
        f"- ready_to_build: {spec.ready_to_build}",
        "",
        f"### Criteria ({len(spec.criteria)})",
    ]
    for crit in spec.criteria:
        parts.extend(_render_criterion(crit))
    if spec.structure is not None:
        parts.append("\n### Structure")
        parts.append(render_structure(spec.structure.root, spec))
    if spec.open_slots:
        parts.append("\n### Open slots (user must answer)")
        parts.extend(
            f"- {s.criterion_id or '—'}.{s.param_name}: {s.question}"
            for s in spec.open_slots
        )
    if spec.dropped:
        parts.append("\n### Dropped criteria")
        parts.extend(f"- {d.text} — {d.reason}" for d in spec.dropped)
    return "\n".join(parts)


def _render_criterion(crit: Criterion) -> list[str]:
    out = [
        f"- `{crit.id}` [{crit.role}] {crit.text} → "
        f"search={crit.search_name or '(unbound)'} (conf={crit.confidence:.2f})",
    ]
    out.extend(f"    {name}={value!r}" for name, value in crit.resolved_params.items())
    out.extend(f"    OPEN {s.param_name}: {s.question}" for s in crit.open_params)
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
        f"- root_count: {o.root_count}",
    ]
    if o.failed_steps:
        parts.append("\n### Failed steps")
        parts.extend(
            f"- {f.step_id} ({f.search_name}): {f.error}" for f in o.failed_steps
        )
    return "\n".join(parts)


def render_verification_full(section: VerificationSection) -> str:
    if section.digest is None:
        return "## Verification\n(not run yet)"
    d = section.digest
    parts = [
        "## Verification (full)",
        f"- success: {d.success}",
        f"- prose: {d.prose}",
    ]
    if d.key_findings:
        parts.append("\n### Key findings")
        parts.extend(f"- {kf}" for kf in d.key_findings)
    if d.caveats:
        parts.append("\n### Caveats")
        parts.extend(f"- {c}" for c in d.caveats)
    return "\n".join(parts)
