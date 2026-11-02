"""The Lead's consult tool, the card a question becomes, and what an answer binds."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType

from assistant_core.graph.tool_summary import with_summary
from assistant_core.graph.turn_state import UserQuestionAnswer
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.card_reply import CardReply
from pathfinder.ai.lead.readings import refused_picks
from pathfinder.ai.lead.recorded_cards import answered_on_the_card, the_card_asked
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.card_answers import (
    spec_bound_by_card,
    spec_with_reading,
)
from pathfinder.domain.strategy.constraints import (
    STRATEGY_SCOPES,
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.expression_handles import shown_wire
from pathfinder.domain.strategy.operator_reading import with_operator
from pathfinder.domain.strategy.question_options import (
    Keep,
    SaveComputedGroups,
    SetOperator,
    SetValues,
    TypedOption,
    Withdraw,
)
from pathfinder.domain.strategy.questions import (
    AskedQuestion,
    OpenQuestion,
    requirement_choices,
)
from pathfinder.domain.strategy.readings import ReadingChooser, ReadValues
from pathfinder.domain.strategy.requirement_reports import numbered_requirements
from pathfinder.services.strategies.sheet_params import sheet_params_for_searches

_LABEL_LIMIT = 120
_QUESTION_LIMIT = 300
_NO_STAND_INS: Mapping[str, Sequence[str]] = MappingProxyType({})


def card_stand_ins(
    questions: Sequence[CardQuestion], requirements: Sequence[Constraint]
) -> dict[str, list[str]]:
    numbered = numbered_requirements(requirements)
    named = [n for q in questions for n in q.replaces]
    unknown = [n for n in named if n not in numbered]
    if unknown:
        msg = (
            f"replaces names {unknown}, which the requirement list does not hold. "
            f"The list holds {', '.join(numbered) or 'none'}; name only those."
        )
        raise ModelRetry(msg)
    scopes = [n for n in named if numbered[n].kind in STRATEGY_SCOPES]
    if scopes:
        msg = (
            f"replaces names {scopes}, an organism or a record type every search "
            f"runs in, which no stand-in takes the place of. Leave them out."
        )
        raise ModelRetry(msg)
    return {
        q.prompt: [numbered[n].id for n in q.replaces] for q in questions if q.replaces
    }


async def consult_can_ask(
    ctx: RunContext[LeadDeps], questions: list[CardQuestion], *, reply: CardReply
) -> None:
    del reply
    cards = ctx.deps.state.turn_markers.card_stand_ins
    call = ctx.tool_call_id or ""
    if call not in cards:
        cards[call] = card_stand_ins(questions, ctx.deps.state.domain.requirements)


def _answer_requirement(
    prompt: str, labels: list[str], note: str, dimension: ConstraintKind
) -> Constraint | None:
    """The words an answer states as a requirement on the question's
    dimension, or None when it states none."""
    stated = "; ".join(labels) if labels else note
    if not stated:
        return None
    return Constraint(
        kind=dimension,
        requested_value=stated,
        # A question carries the label. An unlabelled one falls back to the
        # answer, because a requirement is always named.
        label=prompt[:_LABEL_LIMIT] or stated[:_LABEL_LIMIT],
        source=ConstraintSource.USER_EXPLICIT,
        hard=True,
    )


def _apply(
    state: PipelineState,
    option: TypedOption,
    sheets: Mapping[str, Sequence[ParameterInfo]],
) -> None:
    domain = state.domain
    spec = domain.operational_spec
    match option.binding:
        case SetValues() as values if spec is not None:
            domain.operational_spec = spec_bound_by_card(
                spec,
                values,
                option_id=option.id,
                sheets=sheets,
                expressions=domain.built_expressions,
            )
        case ReadValues() as read if spec is not None:
            values = SetValues(criterion_id=read.criterion_id, params=read.params)
            bound = spec_bound_by_card(
                spec,
                values,
                option_id=option.id,
                sheets=sheets,
                expressions=domain.built_expressions,
            )
            domain.operational_spec = spec_with_reading(
                bound,
                read.criterion_id,
                read.accepted(ReadingChooser.RESEARCHER_ON_A_CARD),
            )
        case Withdraw(constraint_id=withdrawn):
            domain.withdraw(c for c in domain.requirements if c.id == withdrawn)
        case SaveComputedGroups(handle=handle, save=True):
            state.turn_markers.saves_asked.append(handle)
        case SetOperator(criteria=criteria, operator=operator) if spec is not None:
            domain.operational_spec = with_operator(spec, criteria, operator)
        case SetValues() | ReadValues() | Keep() | SaveComputedGroups() | SetOperator():
            pass


def apply_option_bindings(
    state: PipelineState,
    answers: list[UserQuestionAnswer],
    asked: Sequence[CardQuestion] = (),
    *,
    sheets: Mapping[str, Sequence[ParameterInfo]],
    replaced: Mapping[str, Sequence[str]] = _NO_STAND_INS,
) -> None:
    """Apply what each picked option binds, with no model in between.

    A value binds, an operator rewires its combine and a withdrawal retires;
    typed words, a picked reading a framing pass named and the note, never
    another offered label, become a requirement on the dimension ``asked`` names. That requirement replaces
    each one ``replaced`` holds under the question's prompt.
    """
    domain = state.domain
    entry = domain.operational_spec
    recorded = {q.question: q for q in domain.open_questions}
    dimensions = {q.prompt: q.dimension for q in asked}
    labels = {q.prompt: {o.label for o in q.options} for q in asked}
    choices = requirement_choices(domain.requirements)
    readings = domain.reading_labels()
    for answer in answers:
        question = recorded.get(answer.prompt)
        options = {o.label: o for o in question.options} if question else choices
        words: list[str] = []
        domain.record_request_text(answer.note)
        for label in answer.chosen_labels:
            option = options.get(label)
            if option is not None:
                _apply(state, option, sheets)
            elif label in readings:
                domain.pick_reading(label)
                words.append(label)
            elif label not in labels.get(answer.prompt, set()):
                domain.record_request_text(label)
                words.append(label)
        dimension = (
            question.dimension
            if question is not None
            else dimensions.get(answer.prompt, ConstraintKind.OTHER)
        )
        stated = _answer_requirement(answer.prompt, words, answer.note, dimension)
        if stated is not None:
            [held] = domain.record_requirements([stated])
            gone = set(replaced.get(answer.prompt, ())) - {held.id}
            domain.withdraw(
                (c for c in domain.requirements if c.id in gone), stand_in=held
            )
    domain.operational_spec = domain.follow_readings(entry, domain.operational_spec)


def _bound_criterion(option: TypedOption) -> str | None:
    match option.binding:
        case (
            SetValues(criterion_id=criterion_id) | ReadValues(criterion_id=criterion_id)
        ):
            return criterion_id
        case _:
            return None


async def _card_sheets(
    state: PipelineState, answers: Sequence[UserQuestionAnswer]
) -> dict[str, list[ParameterInfo]]:
    """The published sheet of each search a picked option binds a value on."""
    spec = state.domain.operational_spec
    recorded = {q.question: q for q in state.domain.open_questions}
    bound = {
        _bound_criterion(option)
        for answer in answers
        if (question := recorded.get(answer.prompt)) is not None
        for option in question.options
        if option.label in answer.chosen_labels
    }
    searches = (
        {c.search_name for c in spec.criteria if c.id in bound and c.search_name}
        if spec is not None
        else set()
    )
    if spec is None or not searches:
        return {}
    return await sheet_params_for_searches(site_id=state.site_id, search_names=searches)


def _chosen(label: str, question: OpenQuestion | None) -> str:
    """The picked label, with the values its option binds."""
    options = question.options if question is not None else []
    option = next((o for o in options if o.label == label), None)
    match option:
        case TypedOption(binding=SetValues(params=params) | ReadValues(params=params)):
            sets = ", ".join(
                f'{name} to "{shown_wire(name, value)}"'
                for name, value in params.items()
            )
            return f"{label} (sets {sets})"
        case _:
            return label


def _format_answers(
    answers: list[UserQuestionAnswer], questions: Sequence[OpenQuestion]
) -> str:
    recorded = {q.question: q for q in questions}
    parts: list[str] = []
    for a in answers:
        question = recorded.get(a.prompt)
        chosen = (
            ", ".join(_chosen(label, question) for label in a.chosen_labels)
            if a.chosen_labels
            else "(free text)"
        )
        line = f'"{a.prompt}" -> {chosen}'
        if a.note:
            line += f" - note: {a.note}"
        parts.append(line)
    return "; ".join(parts)


def _asked(questions: Sequence[CardQuestion]) -> list[OpenQuestion]:
    """The card's questions as the thread holds an answered one."""
    return [
        AskedQuestion(
            question=q.prompt[:_QUESTION_LIMIT],
            dimension=q.dimension,
            options=[o.label for o in q.options],
        ).typed()
        for q in questions
        if q.prompt
    ]


async def consult_user(
    ctx: RunContext[LeadDeps],
    questions: list[CardQuestion],
    *,
    reply: CardReply,
) -> ToolReturn[list[UserQuestionAnswer]]:
    """Ask the user design questions that SHAPE the investigation, before a
    plan is built. Use this whenever a real fork exists - which searches to
    combine, a threshold that changes the steps, whether to add an arm -
    instead of guessing or bundling the choice into plan approval.

    A question FRAME or an edit recorded is asked exactly as the result's
    ``cardQuestions`` state it: its prompt and its option labels, each of
    which binds a value. A question of your own may offer options; a picked
    one that binds no recorded value comes back as the researcher's words,
    as an answer in the free-text note does. 'Drop <requirement>' and 'Keep
    <requirement>' bind a requirement the conversation holds, and a reading a
    framing pass named, offered as written, states that reading. A question
    that asks for a stand-in names in ``replaces`` the numbers of the ledger's
    requirements the stand-in takes the place of.

    This pauses the turn: the user answers each question in a carousel
    (options + optional free-text note). A picked value is bound into the
    spec before you read the answers; the rest come back to you as hard
    constraints, so you can run (or re-run) ``frame_problem``, or
    ``edit_strategy`` over a strategy that holds a step. Ask only the few
    questions that genuinely change the answer; pick sensible defaults for
    everything else and state your assumptions in ``reply``, which streams
    above the card as the turn's reply. Do NOT ask "submit or request
    changes?" - the approval card already offers both. Background for a
    question goes in that question's ``context``.
    """
    del reply
    state = ctx.deps.state
    shown = the_card_asked(questions, state.domain.open_questions)
    pending = state.pending_approval
    card = "" if pending is None else pending.tool_call_id
    answers = answered_on_the_card(state.user_question_answers.get(card, []), shown)
    asked = with_summary(
        answers,
        f"{len(questions)} questions asked",
        ctx=ctx,
    )
    refused = await refused_picks(state, answers)
    answered = "; ".join(
        [
            _format_answers(answers, state.domain.open_questions),
            *(
                f"the site refused {label!r}, so it binds nothing: {why}"
                for label, why in refused.items()
            ),
        ]
    )
    answers = [
        a.model_copy(
            update={"chosen_labels": [x for x in a.chosen_labels if x not in refused]}
        )
        for a in answers
    ]
    if answers:
        # Their answers are new requirements, so one more frame is licensed.
        state.turn_markers.framed = False
        state.turn_markers.consulted = True
        apply_option_bindings(
            state,
            answers,
            shown,
            sheets=await _card_sheets(state, answers),
            replaced=state.turn_markers.card_stand_ins.get(ctx.tool_call_id or "", {}),
        )
        state.domain.answer_open_questions(answered, on_card=True)
        state.domain.record_answered(_asked(shown))
    return asked
