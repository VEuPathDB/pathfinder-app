from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field

from pathfinder.ai.lead.intent import UserIntent
from pathfinder.ai.lead.ledger_render import (
    render_build_full,
    render_constraints_full,
    render_frame_full,
    render_verification_full,
)
from pathfinder.ai.lead.ledger_sections import (
    BuildSection,
    ConstraintSection,
    FrameSection,
    VerificationSection,
)
from pathfinder.ai.lead.phase_stop import PhaseStop
from pathfinder.ai.lead.proposal import DeclinedProposal
from pathfinder.ai.lead.turn_briefing import ANALYSIS_CHANGED_AFTER_THE_CARD
from pathfinder.domain.caveats import BuildCaveat
from pathfinder.domain.eda_thread import OpenEdaAnalysis
from pathfinder.domain.strategy.operational_spec import (
    DroppedCriterion,
)


def build_contradiction(
    build: BuildSection, *, built_step_count: int
) -> BuildCaveat | None:
    """The build's counts when a success verdict cannot stand over it, or None.

    The ledger records what reached VEuPathDB. A digest may add detail to it
    and may never overrule it.
    """
    if build.outcome is None:
        if built_step_count:
            return None
        return BuildCaveat(pushed=0, failed=0, skipped=0, empty=0)
    if build.is_clean():
        return None
    return BuildCaveat(
        pushed=build.pushed_count,
        failed=build.failed_count,
        skipped=build.skipped_count,
        empty=len(build.zero_result_steps),
    )


def _drop_line(entry: DroppedCriterion) -> str:
    return f"  - {entry.text}: {entry.reason}"


class InvestigationLedger(CamelModel):
    """State of one investigation, read in full by the Lead each turn.

    Sub-agents receive scoped slices through typed work orders instead.
    The ledger is derived from pipeline state, not persisted.
    """

    user_intent: UserIntent | None
    frame: FrameSection
    build: BuildSection
    verification: VerificationSection
    constraints: ConstraintSection = Field(default_factory=ConstraintSection)
    # The last proposal card the researcher declined.
    declined_proposal: DeclinedProposal | None = None
    # Why the last dispatch of this turn ended without a delta. It stays off the
    # wire: the Lead's prose is what a reader needs, not a second copy of it.
    phase_stop: PhaseStop | None = Field(default=None, exclude=True)
    # The analysis the thread holds open. It stays off the wire: the thread's
    # own card shows it to a reader.
    open_analysis: OpenEdaAnalysis | None = Field(default=None, exclude=True)

    def _drop_reasons(self) -> list[str]:
        """Each dropped criterion with the reason the drop recorded.

        A drop hands the criterion back to the Lead, which needs the reason to
        decide what answers it instead.
        """
        spec = self.frame.spec
        if spec is None:
            return []
        return [_drop_line(entry) for entry in spec.dropped]

    def render_summary(self) -> str:
        """Render the compact markdown view the Lead reads in pinned context.

        Counts, derived booleans and the reason of each dropped criterion.
        """
        intent = self.user_intent
        pending = self.verification.pending_checks
        intent_line = (
            f"- intent: {intent.classification.value}; paraphrase, not the "
            f"request: {intent.inferred_goal[:120]}"
            if intent is not None
            else "- intent: not classified yet"
        )
        diff_line = (
            f"  differential: {intent.differential_sides}"
            if intent is not None
            and intent.is_differential
            and intent.differential_sides
            else ""
        )
        lines = ["# Investigation Ledger", intent_line]
        if diff_line:
            lines.append(diff_line)
        if self.phase_stop is not None:
            lines.append(f"- stopped: {self.phase_stop.render()}")
        spec_diff = self.frame.spec_diff()
        lines.extend(
            [
                "",
                "## Frame",
                f"- present: {self.frame.present}",
                (
                    f"- criteria: {self.frame.criteria_count} "
                    f"(bound: {self.frame.bound_count})"
                ),
                *(
                    [f"- this turn: {spec_diff.render()}"]
                    if spec_diff is not None
                    else []
                ),
                f"- dropped: {self.frame.dropped_count}",
                *self._drop_reasons(),
                f"- open_slots: {self.frame.open_slot_count}",
                f"- needs_user: {self.frame.needs_user}",
                f"- ready_to_build: {self.frame.ready_to_build}",
                "",
                "## Build",
                *(
                    [self.build.stale_build.render()]
                    if self.build.stale_build is not None
                    else []
                ),
                f"- pushed: {self.build.pushed_count}",
                f"- failed: {self.build.failed_count}",
                f"- skipped: {self.build.skipped_count}",
                f"- zero_result_steps: {len(self.build.zero_result_steps)}",
                f"- needs_recovery: {self.build.needs_recovery}",
                f"- recovery_kind: {self.build.recovery_kind}",
                f"- succeeded: {self.build.succeeded}",
                "",
                "## Verification",
                f"- complete: {self.verification.complete}",
                f"- successful: {self.verification.successful}",
                *([f"- pending_checks: {', '.join(pending)}"] if pending else []),
                *self._check_lines(),
                "",
                "## Constraints",
                f"- blocking: {self.constraints.blocking}",
                f"- unmet (user-explicit): {self.constraints.unmet_count}",
                "### Stated by the user, oldest first",
                *(self.constraints.render_stated() or ["- (none)"]),
            ]
        )
        composed = self.constraints.render_composed()
        if composed:
            lines.extend(["### Captured for the user, not stated by them", *composed])
        recommended = self.constraints.render_recommended()
        if recommended:
            lines.extend(
                ["### Recommended by you, not replaced by the user", *recommended]
            )
        lines.extend(self._open_analysis_lines())
        lines.extend(self._declined_proposal_lines())
        return "\n".join(lines)

    def _check_lines(self) -> list[str]:
        """Each gap and each caveat of the last check, as the reply states them."""
        digest = self.verification.digest
        if digest is None:
            return []
        return [
            *(f"- gap: {gap.sentence}" for gap in digest.gaps),
            *(f"- caveat: {caveat.sentence}" for caveat in self.verification.caveats),
        ]

    def _open_analysis_lines(self) -> list[str]:
        """The analysis the thread holds open, and whether it moved past its card."""
        analysis = self.open_analysis
        if analysis is None:
            return []
        counted = "counted" if analysis.subset_previewed else "not counted"
        return [
            "",
            "## Open analysis",
            f"- {analysis.dataset_id} ({analysis.analysis_id}), subset {counted}",
            *(
                [f"- {ANALYSIS_CHANGED_AFTER_THE_CARD}"]
                if analysis.changed_after_the_card
                else []
            ),
        ]

    def _declined_proposal_lines(self) -> list[str]:
        """The card the researcher said no to, until a later card is accepted."""
        declined = self.declined_proposal
        if declined is None:
            return []
        return [
            "",
            "## Declined proposal",
            f"- asked: {declined.question}",
            *(f"  - {change.sentence}" for change in declined.proposed_changes),
            *(
                [f"- the researcher's comment: {declined.note}"]
                if declined.note
                else []
            ),
            "- it is offered again only on a new card",
        ]

    def render_section(self, section: str) -> str:
        """Render the full detail of one section."""
        if section == "frame":
            return render_frame_full(self.frame)
        if section == "build":
            return render_build_full(self.build)
        if section == "verification":
            return render_verification_full(self.verification)
        if section == "constraints":
            return render_constraints_full(self.constraints)
        msg = f"unknown section: {section}"
        raise ValueError(msg)
