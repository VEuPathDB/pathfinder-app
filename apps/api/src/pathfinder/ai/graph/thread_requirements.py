"""What a thread requires, what it asked and what retired a requirement."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pathfinder.ai.graph.stored_requirement_keys import (
    ids_by_stored_key,
    markers_by_id,
    questions_by_id,
    retired_by_id,
)
from pathfinder.ai.graph.turn_records import AnsweredQuestions, TurnMarkers
from pathfinder.ai.lead.intent import UserIntent
from pathfinder.domain.strategy.card_answers import spec_with_reading
from pathfinder.domain.strategy.chosen_reading import ChosenReading
from pathfinder.domain.strategy.constraints import (
    STRATEGY_SCOPES,
    Constraint,
    ConstraintKind,
    ConstraintSource,
    OrganismValue,
    StoredConstraint,
)
from pathfinder.domain.strategy.named_groups import GroupScope
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.organism_picks import OrganismPick, unnamed_organisms
from pathfinder.domain.strategy.question_options import PickTail, TailRule
from pathfinder.domain.strategy.questions import (
    OpenQuestion,
    standing_recommendations,
)
from pathfinder.domain.strategy.reading_plan import OfferedReading, label_built_by
from pathfinder.domain.strategy.readings import AcceptedReading
from pathfinder.domain.strategy.requirement_lifecycle import (
    RetiredRequirement,
    reopened,
    restored,
    retire,
)
from pathfinder.domain.strategy.stated_requirements import (
    RecordedRequirements,
    attributed,
    identified,
    with_requirements,
)


class ThreadRequirements(BaseModel):
    """The requirements, the questions and the recommendations of one thread,
    and the markers of the message that last changed them."""

    # A conversation saved by an earlier build may carry a field this build
    # dropped; the value is discarded and the rest of the state is rebuilt.
    model_config = ConfigDict(
        arbitrary_types_allowed=True, extra="ignore", revalidate_instances="always"
    )

    turn_markers: TurnMarkers = Field(default_factory=TurnMarkers)
    # Every requirement the thread has stated, oldest first. A clarification
    # adds to this list; only a message that abandons the request clears it.
    requirements: list[StoredConstraint] = Field(default_factory=list)
    # The requirements a message withdrew or replaced, each with its
    # lifecycle. A check reports none as a gap.
    retired_requirements: list[RetiredRequirement] = Field(default_factory=list)
    group_scopes: dict[str, GroupScope] = Field(default_factory=dict)
    # Every question an answer settled. A question is never a requirement, so
    # a check that restates one reports no gap.
    answered_questions: list[OpenQuestion] = Field(default_factory=list)
    # What the thread asked the user and has not heard back on, with the value
    # each question recommended.
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    # The recommended values the thread's requirements leave standing. A
    # requirement on the same dimension replaces one.
    recommendations: list[StoredConstraint] = Field(default_factory=list)
    named_readings: list[ChosenReading] = Field(default_factory=list)
    offered_readings: dict[str, OfferedReading] = Field(default_factory=dict)
    picked_readings: list[str] = Field(default_factory=list)
    card_picks: list[str] = Field(default_factory=list)
    tail_picks: dict[str, PickTail] = Field(default_factory=dict)
    organism_picks: list[OrganismPick] = Field(default_factory=list)

    @model_validator(mode="after")
    def _names_each_requirement_by_id(self) -> ThreadRequirements:
        ids = ids_by_stored_key(self._recorded())
        self.retired_requirements = retired_by_id(self.retired_requirements, ids)
        self.open_questions = questions_by_id(self.open_questions, ids)
        self.answered_questions = questions_by_id(self.answered_questions, ids)
        self.turn_markers = markers_by_id(self.turn_markers, ids)
        return self

    def name_reading(self, reading: ChosenReading | None) -> None:
        if reading is not None and reading not in self.named_readings:
            self.named_readings.append(reading)

    def offer_reading(self, offered: OfferedReading) -> None:
        self.offered_readings[offered.label] = offered

    def picked_offer(self, message: str) -> OfferedReading | None:
        """The plan Explore offered that this message builds, else the one a
        card answer picked last."""
        for label in (label_built_by(message), *reversed(self.picked_readings)):
            if label is not None and label in self.offered_readings:
                return self.offered_readings[label]
        return None

    def pick_reading(self, label: str) -> None:
        if label not in self.picked_readings:
            self.picked_readings.append(label)

    def pick_on_a_card(self, label: str) -> None:
        if label not in self.card_picks:
            self.card_picks.append(label)

    def hold_tail_pick(self, label: str, pick: PickTail) -> None:
        self.tail_picks[label] = pick

    def tail_rules_on(self, variable_name: str) -> dict[str, TailRule]:
        return {
            label: pick.rule
            for label, pick in self.tail_picks.items()
            if pick.variable_name == variable_name
        }

    def reading_labels(self) -> list[str]:
        return list(
            dict.fromkeys(label for r in self.named_readings for label in r.labels())
        )

    def answer_open_questions(self, answer: str, *, on_card: bool = False) -> None:
        """Close every question open now, whatever the answer says.

        A card answers the questions a pass asked under this same message.
        """
        self._answer(self.open_questions, answer, on_card=on_card)

    def answer_the_questions_at_arrival(self, answer: str) -> None:
        """Close the questions this message found open, and no later one."""
        arrived = set(self.turn_markers.questions_at_arrival)
        self._answer([q for q in self.open_questions if q.question in arrived], answer)

    def _answer(
        self, questions: list[OpenQuestion], answer: str, *, on_card: bool = False
    ) -> None:
        # A later answer under the same message replaces the record, because
        # the draft already holds what the earlier one decided.
        if not questions:
            return
        self.turn_markers.answered = AnsweredQuestions(
            questions=questions, answer=answer, on_card=on_card
        )
        self.open_questions = [q for q in self.open_questions if q not in questions]
        self.record_answered(questions)

    def record_answered(self, questions: Iterable[OpenQuestion]) -> None:
        """Hold each answered question once, by its words."""
        held = {q.question for q in self.answered_questions}
        for question in questions:
            if question.question not in held:
                held.add(question.question)
                self.answered_questions.append(question)

    def record_questions(self, questions: Iterable[OpenQuestion]) -> None:
        """Hold each question once, with the options its newest asking offers."""
        for question in questions:
            held = [q.question for q in self.open_questions]
            if question.question in held:
                self.open_questions[held.index(question.question)] = question
            else:
                self.open_questions.append(question)

    def record_recommendations(self) -> None:
        """Keep the recommendations the thread's requirements leave standing.

        An accepted recommendation is recorded once, so a later reply that asks
        something else does not drop it.
        """
        replaced = {c.kind for c in self.requirements}
        held = [c for c in self.recommendations if c.kind not in replaced]
        seen = {(c.kind, c.requested_value) for c in held}
        for offered in standing_recommendations(self.open_questions, self.requirements):
            key = (offered.kind, offered.requested_value)
            if key in seen:
                continue
            seen.add(key)
            held.append(offered)
        self.recommendations = held

    def record(self, intent: UserIntent, messages: Sequence[str]) -> None:
        """Take what this message states and the held requirements it withdraws
        by id. ``messages`` are the researcher's words, this message first."""
        held = list(self.requirements)
        stated = identified(
            attributed(intent.explicit_constraints, messages), self._recorded()
        )
        self._record(with_requirements(held, stated))
        still_held = [c for c in self.requirements if c in held]
        added = [c for c in self.requirements if c not in held]
        self.withdraw(
            (c for c in still_held if c.id in intent.withdrawn_ids), stated=added
        )
        self.turn_markers.requirements_added.extend(added)
        self.record_recommendations()

    def withdraw_this_messages_requirements(self) -> None:
        """Undo what this message asked for, once the researcher said no to it."""
        added = self.turn_markers.requirements_added
        back, self.retired_requirements = restored(
            self.retired_requirements,
            turn_id=self._turn_id(),
            dropped=[c.id for c in added],
        )
        kept = [c for c in self.requirements if c not in added]
        self._record(with_requirements(kept, back))
        self.turn_markers.requirements_added = []

    def record_requirements(
        self, constraints: Iterable[Constraint]
    ) -> list[Constraint]:
        """Add each requirement the thread has not stated already, in place of
        a held one of the same single-valued kind, and return each as held."""
        held = identified(constraints, self._recorded())
        self._record(with_requirements(self.requirements, held))
        return held

    def _recorded(self) -> list[Constraint]:
        return [*self.requirements, *(r.constraint for r in self.retired_requirements)]

    def _record(self, recorded: RecordedRequirements) -> None:
        self.requirements = recorded.live
        displaced = {r.constraint.id for r in recorded.displaced}
        self.retired_requirements = [
            *(
                r
                for r in reopened(self.retired_requirements, recorded.live)
                if r.constraint.id not in displaced
            ),
            *recorded.displaced,
        ]

    def withdraw(
        self,
        requirements: Iterable[Constraint],
        *,
        stated: Sequence[Constraint] = (),
        stand_in: Constraint | None = None,
    ) -> None:
        """Retire each of these held requirements on this message: replaced by
        the chosen ``stand_in``, else by a value of its kind the message
        ``stated``, else withdrawn."""
        self.requirements, self.retired_requirements = retire(
            self.requirements,
            self.retired_requirements,
            list(requirements),
            turn_id=self._turn_id(),
            stated=stated,
            stand_in=stand_in,
        )

    def accept_reading(
        self, spec: OperationalSpec, criterion_id: str, accepted: AcceptedReading
    ) -> OperationalSpec:
        question = self._offering(criterion_id, accepted.reading)
        if question is None:
            return spec_with_reading(spec, criterion_id, accepted)
        dimension = question.dimension
        [stand_in] = self.record_requirements(
            [
                Constraint(
                    kind=ConstraintKind.UNTYPED
                    if dimension in STRATEGY_SCOPES
                    else dimension,
                    requested_value=accepted.reading,
                    label=question.question,
                    source=ConstraintSource.USER_EXPLICIT,
                    hard=True,
                )
            ]
        )
        self.withdraw(
            (
                c
                for c in self.requirements
                if c.id in accepted.replaces
                and c.id != stand_in.id
                and c.kind not in STRATEGY_SCOPES
            ),
            stand_in=stand_in,
        )
        held = accepted.model_copy(update={"stand_in": stand_in.id})
        return spec_with_reading(spec, criterion_id, held)

    def follow_readings(
        self, before: OperationalSpec | None, after: OperationalSpec | None
    ) -> OperationalSpec | None:
        was, now = _held_readings(before), _held_readings(after)
        ended = {
            r.stand_in
            for cid, r in was.items()
            if r.stand_in and not r.same_reading(now.get(cid))
        }
        self.withdraw(c for c in self.requirements if c.id in ended)
        for cid, held in now.items():
            if after is not None and not held.same_reading(was.get(cid)):
                after = self.accept_reading(after, cid, held)
        return after

    def _offering(self, criterion_id: str, reading: str) -> OpenQuestion | None:
        answered = self.turn_markers.answered
        asked = [
            *self.open_questions,
            *([] if answered is None else answered.questions),
            *reversed(self.answered_questions),
        ]
        return next(
            (
                q
                for q in asked
                for o in q.options
                if (offered := o.offered_reading()) is not None
                and offered.criterion_id == criterion_id
                and offered.reading == reading
            ),
            None,
        )

    def retire_what_a_delete_leaves_unanswered(
        self, deleted: Sequence[Criterion], remaining: Sequence[Criterion]
    ) -> None:
        """Withdraw each live requirement a deleted criterion links and no
        remaining one links, a combination among them. An organism or a record
        type scopes the whole strategy, so a delete withdraws neither."""
        self.withdraw(
            c
            for c in self.requirements
            if c.kind not in STRATEGY_SCOPES
            and any(d.links(c.id) for d in deleted)
            and not any(r.links(c.id) for r in remaining)
        )

    def hold_organism_picks(self, picks: Sequence[OrganismPick]) -> None:
        unnamed = {c.quote for c in unnamed_organisms(self.requirements)}
        asked = {p.quote for p in picks}
        self.organism_picks = [
            p
            for p in [
                *(p for p in self.organism_picks if p.quote not in asked),
                *picks,
            ]
            if p.quote in unnamed
        ]

    def name_organisms_from(self, organisms: Sequence[str]) -> None:
        """Name each organism the request left open by the one entry of
        ``organisms`` its words lead."""
        for requirement in unnamed_organisms(self.requirements):
            words = requirement.requested_value.casefold()
            named = {o for o in organisms if o.casefold().startswith(words)}
            if len(named) == 1:
                self.name_organism(requirement.id, named.pop())

    def name_organism(self, requirement_id: str, organism: str) -> None:
        self.requirements = [
            c.model_copy(
                update={
                    "requested_value": organism,
                    "value": OrganismValue(organism=organism),
                }
            )
            if c.id == requirement_id and c.kind is ConstraintKind.ORGANISM
            else c
            for c in self.requirements
        ]

    def recorded_by_id(self, ids: Collection[str]) -> list[Constraint]:
        return [c for c in self._recorded() if c.id in ids]

    def _turn_id(self) -> str:
        return str(self.turn_markers.message_id or "")


def _held_readings(spec: OperationalSpec | None) -> dict[str, AcceptedReading]:
    return {
        c.id: held
        for c in ([] if spec is None else spec.criteria)
        if (held := c.held_reading) is not None
    }
