"""The four sections an investigation ledger is built from."""

from __future__ import annotations

from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import Field
from veupathdb.domain.parameters import (
    to_wire,
)
from veupathdb_mcp.catalog import contrast_role_of, is_direction_param

from pathfinder.ai.graph.state import VerificationDigest
from pathfinder.domain.caveats import Caveat
from pathfinder.domain.strategy.build_outcome import BuildOutcome, NodeResult
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    GroundedConstraint,
    is_blocking,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
    StructureNode,
    plain_value,
)
from pathfinder.domain.strategy.spec_diff import SpecDiff, diff_specs
from pathfinder.domain.strategy.staleness import StaleBuild

RecoveryKind = Literal[
    "none",
    "transient_retry",
    "param_replan",
    "search_replan",
    "user_clarify",
]
SubAgentName = Literal[
    "frame",
    "build",
    "execute_recovery",
    "verify",
    "validate",
    "research",
]


class ContrastSummary(CamelModel):
    """Which way a differential criterion points.

    WDK computes fold change as comparator against reference. A swap of the two
    inverts the biology and still returns a plausible gene set.
    """

    criterion_id: str
    comparator: str | None = None
    reference: str | None = None
    direction: str | None = None

    @computed
    def summary(self) -> str:
        subject = self.comparator or "(unset)"
        baseline = self.reference or "(unset)"
        lead = f"{self.direction} in " if self.direction else ""
        return f"{lead}{subject} vs {baseline}"


def _contrast_for(crit: Criterion) -> ContrastSummary | None:
    comparator: str | None = None
    reference: str | None = None
    direction: str | None = None
    for name, value in crit.param_values.items():
        role = contrast_role_of(name)
        if role == "comparison":
            comparator = plain_value(value)
        elif role == "reference":
            reference = plain_value(value)
        elif is_direction_param(name):
            direction = plain_value(value)
    if comparator is None and reference is None:
        return None
    return ContrastSummary(
        criterion_id=crit.id,
        comparator=comparator,
        reference=reference,
        direction=direction,
    )


def render_structure(node: StructureNode, spec: OperationalSpec) -> str:
    by_id = {c.id: c for c in spec.criteria}
    if node.kind in {"leaf", "transform"}:
        crit = by_id.get(node.criterion_id or "")
        name = (
            crit.search_name
            if crit and crit.search_name
            else (node.criterion_id or "?")
        )
        if node.kind == "transform":
            inner = render_structure(node.inputs[0], spec) if node.inputs else "?"
            return f"{name}({inner})"
        return name
    if node.kind == "copy":
        inner = render_structure(node.inputs[0], spec) if node.inputs else "?"
        return f"COPY {inner}"
    op = node.operator.value if node.operator else "?"
    inner = f" {op} ".join(render_structure(child, spec) for child in node.inputs)
    return f"({inner})"


class FrameSection(CamelModel):
    """The OperationalSpec the FRAME phase produced.

    It holds criteria bound to WDK searches with resolved params and a
    combine structure.
    """

    spec: OperationalSpec | None = None
    # The spec the turn started from. It stays off the wire: the comparison is
    # what a reader needs, and a second whole spec per chunk is not.
    spec_before_turn: OperationalSpec | None = Field(default=None, exclude=True)

    @computed
    def present(self) -> bool:
        return self.spec is not None

    def spec_diff(self) -> SpecDiff | None:
        """What this turn did to the spec it started from, or None on a fresh
        turn. Every claim that a criterion was preserved is read from here."""
        before = self.spec_before_turn
        if self.spec is None or before is None or not before.criteria:
            return None
        return diff_specs(before, self.spec)

    @computed
    def diff(self) -> SpecDiff | None:
        return self.spec_diff()

    @computed
    def criteria_count(self) -> int:
        return len(self.spec.criteria) if self.spec else 0

    @computed
    def bound_count(self) -> int:
        return sum(1 for c in self.spec.criteria if c.bound) if self.spec else 0

    def open_slots(self) -> list[OpenSlot]:
        """Every value the spec leaves for the user: its own slots and each
        criterion's."""
        if self.spec is None:
            return []
        return [
            *self.spec.open_slots,
            *(slot for c in self.spec.criteria for slot in c.open_params),
        ]

    @computed
    def open_slot_count(self) -> int:
        return len(self.open_slots())

    @computed
    def dropped_count(self) -> int:
        return len(self.spec.dropped) if self.spec else 0

    @computed
    def ready_to_build(self) -> bool:
        return self.spec.ready_to_build if self.spec else False

    @computed
    def needs_user(self) -> bool:
        return bool(self.open_slots())

    @computed
    def contrasts(self) -> list[ContrastSummary]:
        """One entry per criterion that contrasts two sample groups."""
        if self.spec is None:
            return []
        found = (_contrast_for(c) for c in self.spec.criteria)
        return [c for c in found if c is not None]

    @computed
    def structure_render(self) -> str | None:
        """Compact combine-tree string for the UI."""
        if self.spec is None or self.spec.structure is None:
            return None
        return render_structure(self.spec.structure.root, self.spec)


class BuildSection(CamelModel):
    outcome: BuildOutcome | None = None
    # Set when a live read shows the strategy changed since this build.
    stale_build: StaleBuild | None = None
    pushed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    zero_result_steps: list[str] = Field(default_factory=list)
    needs_recovery: bool = False
    recovery_kind: RecoveryKind = "none"

    def is_clean(self) -> bool:
        """A build ran and every step it named reached VEuPathDB non-empty."""
        return (
            self.outcome is not None
            and self.failed_count == 0
            and self.skipped_count == 0
            and not self.zero_result_steps
        )

    @computed
    def succeeded(self) -> bool:
        return self.is_clean()

    @computed
    def node_results(self) -> list[NodeResult]:
        """Per-node build detail for the UI."""
        return list(self.outcome.node_results) if self.outcome else []

    @computed
    def wdk_strategy_id(self) -> int | None:
        return self.outcome.wdk_strategy_id if self.outcome else None


class VerificationSection(CamelModel):
    digest: VerificationDigest | None = None
    # The digest's caveats, then each value of the spec that narrows its step.
    # Empty while no check has run.
    caveats: list[Caveat] = Field(default_factory=list)

    @computed
    def complete(self) -> bool:
        return self.digest is not None

    @computed
    def successful(self) -> bool:
        return self.digest is not None and self.digest.passed

    @property
    def pending_checks(self) -> list[str]:
        """The steps a passing check could not read, empty after an objection."""
        digest = self.digest
        return [] if digest is None or not digest.success else digest.pending_checks


def assumption_constraints(spec: OperationalSpec | None) -> list[GroundedConstraint]:
    """The criteria's chosen values, as constraints the user can override.

    A chosen value is what the model set where the request said nothing, so it
    is grounded by construction and never blocks.
    """
    if spec is None:
        return []
    return [
        GroundedConstraint(
            constraint=Constraint(
                kind=ConstraintKind.OTHER,
                requested_value=to_wire(chosen.value),
                label=name,
                source=ConstraintSource.ASSUMED,
                hard=False,
            ),
            status=ConstraintStatus.GROUNDED,
            realized_value=to_wire(chosen.value),
            note=chosen.basis,
        )
        for criterion in spec.criteria
        for name, chosen in criterion.set_by("chosen").items()
    ]


def unexpressed_constraints(spec: OperationalSpec | None) -> list[GroundedConstraint]:
    """The texts the spec states that no search its pass read can state.

    Each is the researcher's own word, or the requirement a drop holds open, so
    it stands unmet and blocks until a search states it.
    """
    if spec is None:
        return []
    return [
        GroundedConstraint(
            constraint=text.requirement
            or Constraint(
                kind=ConstraintKind.OTHER,
                requested_value=text.word,
                label=text.stated_in[:_UNEXPRESSED_LABEL],
                source=ConstraintSource.USER_EXPLICIT,
                hard=True,
            ),
            status=ConstraintStatus.UNGROUNDABLE,
            note=text.why,
        )
        for text in spec.unexpressed()
    ]


def unexpressed_words(spec: OperationalSpec | None) -> list[str]:
    """Every word the spec states and no search it read can state."""
    if spec is None:
        return []
    return [text.word for text in spec.unexpressed()]


_UNEXPRESSED_LABEL = 120

# How many requirements the pinned summary prints before it counts the rest.
_STATED_WINDOW = 20


def _windowed(lines: list[str], *, how: str) -> list[str]:
    """The most recent lines, with a count of the ones left out and how they came."""
    elided = max(0, len(lines) - _STATED_WINDOW)
    if not elided:
        return lines
    return [f"- ({elided} more {how} earlier)", *lines[elided:]]


class ConstraintSection(CamelModel):
    grounded: list[GroundedConstraint] = Field(default_factory=list)
    # Values the assistant recommended that the latest message leaves standing.
    # They stay off the wire: the reply that offered them is what a reader has.
    recommended: list[Constraint] = Field(default_factory=list, exclude=True)
    # The requirements an earlier message stated. Off the wire: the render is
    # what marks them, and the constraint itself is already carried above.
    carried: list[Constraint] = Field(default_factory=list, exclude=True)
    # The requirements the thread captured that the user did not state. Off the
    # wire for the same reason: they are already in ``grounded``.
    composed: list[Constraint] = Field(default_factory=list, exclude=True)

    def render_recommended(self) -> list[str]:
        """One line per recommendation the user has not replaced."""
        return [
            f"- {c.label} ({c.kind}): {c.requested_value!r}" for c in self.recommended
        ]

    def render_composed(self) -> list[str]:
        """One line per requirement the thread captured for the user."""
        return _windowed(
            [f"- {c.label} ({c.kind}): {c.requested_value!r}" for c in self.composed],
            how="captured",
        )

    def render_stated(self) -> list[str]:
        """One line per requirement the user stated, newest last.

        A requirement an earlier message stated says so. The pinned summary is
        bounded, so a long thread shows the most recent window and counts the
        rest.
        """
        stated = [
            g
            for g in self.grounded
            if g.constraint.source is ConstraintSource.USER_EXPLICIT
        ]
        carried = {(c.kind, c.requested_value) for c in self.carried}
        return _windowed(
            [
                f"- {g.constraint.label} ({g.constraint.kind}): "
                f"{g.constraint.requested_value!r} -> {g.status}"
                + (
                    " (from an earlier message)"
                    if (g.constraint.kind, g.constraint.requested_value) in carried
                    else ""
                )
                for g in stated
            ],
            how="stated",
        )

    @computed
    def unmet_count(self) -> int:
        return sum(1 for g in self.grounded if is_blocking(g))

    @computed
    def blocking(self) -> bool:
        return any(is_blocking(g) for g in self.grounded)
