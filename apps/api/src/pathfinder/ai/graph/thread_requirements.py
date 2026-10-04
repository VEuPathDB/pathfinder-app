"""What a thread requires, what it asked and what retired a requirement."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field

from pathfinder.ai.graph.turn_records import AnsweredQuestions, TurnMarkers
from pathfinder.ai.lead.intent import UserIntent
from pathfinder.domain.strategy.constraints import (
    STRATEGY_SCOPES,
    Constraint,
    states_the_content,
)
from pathfinder.domain.strategy.message_reading import (
    adds_an_alternative,
    message_states_constraint,
)
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.questions import (
    OpenQuestion,
    standing_recommendations,
)
from pathfinder.domain.strategy.requirement_lifecycle import (
    RetiredRequirement,
    reopened,
    restored,
    retire,
    retire_dropped_sides,
    with_recorded_sources,
    withdrawn_by,
)
from pathfinder.domain.strategy.stated_requirements import (
    RecordedRequirements,
    attributed,
    with_requirements,
)


class ThreadRequirements(BaseModel):
    """The requirements, the questions and the recommendations of one thread,
    and the markers of the message that last changed them."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    turn_markers: TurnMarkers = Field(default_factory=TurnMarkers)
    # Every requirement the thread has stated, oldest first. A clarification
    # adds to this list; only a message that abandons the request clears it.
    requirements: list[Constraint] = Field(default_factory=list)
    # The requirements a message withdrew or replaced, each with its
    # lifecycle. A check reports none as a gap.
    retired_requirements: list[RetiredRequirement] = Field(default_factory=list)
    # Every question an answer settled. A question is never a requirement, so
    # a check that restates one reports no gap.
    answered_questions: list[OpenQuestion] = Field(default_factory=list)
    # What the thread asked the user and has not heard back on, with the value
    # each question recommended.
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    # The recommended values the thread's requirements leave standing. A
    # requirement on the same dimension replaces one.
    recommendations: list[Constraint] = Field(default_factory=list)

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
        """Take what this message states and withdraws. ``messages`` are the
        researcher's words, this message first. A value only an ask of the
        message carries is no requirement, and a question is all ask."""
        held = list(self.requirements)
        newest = messages[0] if messages else ""
        asks = [ask.text for ask in intent.researcher_asks(newest)]
        stated = [
            c
            for c in attributed(intent.explicit_constraints, messages, held)
            if not _only_asked(c, newest, asks)
        ]
        self._record(
            with_requirements(
                held, stated, adds_alternatives=adds_an_alternative(newest)
            )
        )
        still_held = [c for c in self.requirements if c in held]
        added = [c for c in self.requirements if c not in held]
        self.withdraw(withdrawn_by(still_held, intent.withdrawn), stated=added)
        self.turn_markers.requirements_added.extend(added)
        self.record_recommendations()

    def withdraw_this_messages_requirements(self) -> None:
        """Undo what this message asked for, once the researcher said no to it."""
        added = self.turn_markers.requirements_added
        back, self.retired_requirements = restored(
            self.retired_requirements,
            turn_id=self._turn_id(),
            dropped=[c.key for c in added],
        )
        kept = [c for c in self.requirements if c not in added]
        self._record(with_requirements(kept, back))
        self.turn_markers.requirements_added = []

    def record_requirements(self, constraints: Iterable[Constraint]) -> None:
        """Add each requirement the thread has not stated already, in place of
        a held one of the same single-valued kind."""
        self._record(with_requirements(self.requirements, constraints))

    def _record(self, recorded: RecordedRequirements) -> None:
        self.requirements = recorded.live
        displaced = {r.constraint.key for r in recorded.displaced}
        self.retired_requirements = [
            *(
                r
                for r in reopened(self.retired_requirements, recorded.live)
                if r.constraint.key not in displaced
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

    def retire_what_a_delete_leaves_unanswered(
        self, deleted: Sequence[Criterion], remaining: Sequence[Criterion]
    ) -> None:
        """Withdraw each live requirement a deleted criterion's text states and
        no remaining one states, and each combination a side of which names a
        deleted criterion. An organism or a record type scopes the whole
        strategy, so a delete withdraws neither."""

        def stated(requirement: Constraint, criteria: Sequence[Criterion]) -> bool:
            return any(
                states_the_content(c.text, requirement.requested_value)
                for c in criteria
            )

        self.withdraw(
            c
            for c in self.requirements
            if c.kind not in STRATEGY_SCOPES
            and stated(c, deleted)
            and not stated(c, remaining)
        )
        self.requirements, self.retired_requirements = retire_dropped_sides(
            self.requirements,
            self.retired_requirements,
            deleted=deleted,
            remaining=remaining,
            turn_id=self._turn_id(),
        )

    def withdrawn_as_recorded(self, intent: UserIntent) -> UserIntent:
        """The intent, each requirement it withdraws in the source this thread
        recorded for it. An intent this changes nothing of stays the same object."""
        recorded = [
            *self.requirements,
            *(r.constraint for r in self.retired_requirements),
        ]
        sourced = with_recorded_sources(intent.withdrawn, recorded)
        if sourced == intent.withdrawn:
            return intent
        return intent.model_copy(update={"withdrawn": sourced})

    def _turn_id(self) -> str:
        return str(self.turn_markers.message_id or "")


def _only_asked(constraint: Constraint, message: str, asks: Sequence[str]) -> bool:
    """Whether an ask of the message carries the value and the rest of the
    message does not."""
    rest = message.casefold()
    for ask in asks:
        rest = rest.replace(ask.casefold(), " ")
    return any(
        message_states_constraint(ask, constraint) for ask in asks
    ) and not message_states_constraint(rest, constraint)
