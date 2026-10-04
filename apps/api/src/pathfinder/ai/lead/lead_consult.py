"""The Lead's consult tool, the card a question becomes, and what an answer binds."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from assistant_core.graph.tool_summary import with_summary
from assistant_core.graph.turn_state import ConsultOption, UserQuestionAnswer
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.card_reply import CardReply
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.card_answers import params_held, spec_bound_by_card
from pathfinder.domain.strategy.constraint_grounding import dimension_of_parameter
from pathfinder.domain.strategy.constraints import (
    CombinationRequest,
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.questions import (
    AskedQuestion,
    Keep,
    OpenQuestion,
    SetValues,
    TypedOption,
    Withdraw,
    requirement_choices,
)
from pathfinder.domain.strategy.requirement_lifecycle import (
    MANY_VALUED_KINDS,
    stood_in_for,
)
from pathfinder.services.strategies.sheet_params import sheet_params_for_searches

_LABEL_LIMIT = 120
_QUESTION_LIMIT = 300


def _recommends(question: OpenQuestion, option: TypedOption) -> bool:
    match option.binding:
        case SetValues(params=params):
            return question.recommended_value in params.values()
        case _:
            return option.label == question.recommended_value


def card_questions(questions: Sequence[OpenQuestion]) -> list[CardQuestion]:
    """The recorded questions as the card asks them, each option by its label."""
    return [
        CardQuestion(
            id=f"q{index}",
            prompt=question.question,
            dimension=question.dimension,
            options=[
                ConsultOption(label=o.label, recommended=_recommends(question, o))
                for o in question.options
            ],
        )
        for index, question in enumerate(questions, 1)
    ]


def _held_dimensions(
    recorded: Sequence[OpenQuestion], spec: OperationalSpec | None
) -> set[ConstraintKind]:
    """The single-valued dimensions a recorded question states or a parameter
    of the spec sets, the organism included while a criterion names it."""
    held = {q.dimension for q in recorded}
    if spec is None:
        return held - MANY_VALUED_KINDS
    if any(c.organism_param for c in spec.criteria):
        held.add(ConstraintKind.ORGANISM)
    names = {c.id: c for c in spec.criteria}
    held |= {
        dimension_of_parameter(
            param, names[cid].display_name_of(param) if cid in names else param
        )
        for cid, params in params_held(spec).items()
        for param in params
    }
    return held - MANY_VALUED_KINDS


def _unbound_labels(question: CardQuestion, choices: Sequence[str]) -> list[str]:
    """The labels of a question of the Lead's own that bind nothing."""
    return [o.label for o in question.options if o.label not in choices]


def refuse_a_card_that_binds_nothing(
    ctx: RunContext[LeadDeps],
    questions: list[CardQuestion],
    *,
    reply: CardReply,
) -> None:
    """Refuse a card that does not ask each recorded binding question as recorded.

    An option the card relabels would bind nothing, so every recorded question
    that offers options is asked with its recorded prompt and labels. A
    question of the Lead's own offers no option, or the drop and keep options
    of a requirement the thread holds; one with no option asks no dimension a
    parameter of the spec holds. A question the researcher answered is never
    asked again.
    """
    del reply
    domain = ctx.deps.state.domain
    recorded = [q for q in domain.open_questions if q.options]
    asked = {q.prompt: {o.label for o in q.options} for q in questions}
    wrong = [
        q for q in recorded if asked.get(q.question) != {o.label for o in q.options}
    ]
    offered = {o.label for q in recorded for o in q.options}
    prompts = {q.question for q in recorded}
    own = [q for q in questions if q.prompt not in prompts]
    reused = [q.prompt for q in own if offered & {o.label for o in q.options}]
    choices = list(requirement_choices(domain.requirements))
    unbound = [
        (q.prompt, labels)
        for q in own
        if q.prompt not in reused and (labels := _unbound_labels(q, choices))
    ]
    held = _held_dimensions(recorded, domain.operational_spec)
    claimed = [q for q in own if not q.options and q.dimension in held]
    decided = {q.question for q in domain.answered_questions}
    again = [q.prompt for q in questions if q.prompt[:_QUESTION_LIMIT] in decided]
    if not wrong and not reused and not unbound and not claimed and not again:
        return
    expected = [
        f"{q.prompt!r} with the options {[o.label for o in q.options]}"
        for q in card_questions(recorded)
    ]
    problems = [
        *(f"{q.question!r} is not asked with its recorded options" for q in wrong),
        *(f"{prompt!r} offers a value a recorded question binds" for prompt in reused),
        *(
            f"{prompt!r} offers {labels}, which bind nothing, so an answer to "
            f"them states nothing"
            for prompt, labels in unbound
        ),
        *(
            f"{q.prompt!r} asks the {q.dimension.value}, which a parameter of the "
            f"spec sets, so an answer in words binds nothing"
            for q in claimed
        ),
        *(f"{prompt!r} was answered already; its answer stands" for prompt in again),
    ]
    got = "; ".join(
        f"{q.prompt!r}: {sorted(o.label for o in q.options)}" for q in questions
    )
    held_choices = ", ".join(repr(label) for label in choices)
    msg = (
        f"The card binds nothing for these questions: {'; '.join(problems)}. The "
        f"card asked {got}. Ask each of these exactly as recorded, in `questions`: "
        f"{'; '.join(expected) or 'none'}. A question of your own offers no "
        f"options, for an answer in the researcher's words about something no "
        f"parameter of the spec sets, or offers 'Drop <requirement>' and 'Keep "
        f"<requirement>' for a requirement the conversation holds. The "
        f"requirements the conversation holds offer: {held_choices or 'none'}. "
        f"A value a "
        f"parameter sets is asked by the pass that binds it: dispatch "
        f"edit_strategy, or frame_problem over a spec with no built step, with "
        f"the question, and ask the card its result carries."
    )
    raise ModelRetry(msg)


def _answer_requirement(
    prompt: str, labels: list[str], note: str, dimension: ConstraintKind
) -> Constraint | None:
    """The words an answer states as a requirement, or None when it states none.

    The requirement states the question's dimension. Words that read as a
    combination expression are typed as one, so the structure gate and the
    verification hold can check it.
    """
    stated = "; ".join(labels) if labels else note
    if not stated:
        return None
    expression = next(
        (t for t in (*labels, note) if CombinationRequest.parse(t) is not None),
        None,
    )
    return Constraint(
        kind=dimension if expression is None else ConstraintKind.COMBINATION,
        requested_value=expression or stated,
        # A question carries the label. An unlabelled one falls back to the
        # answer, because a requirement is always named.
        label=prompt[:_LABEL_LIMIT] or stated[:_LABEL_LIMIT],
        source=ConstraintSource.USER_EXPLICIT,
        hard=True,
    )


def apply_option_bindings(
    state: PipelineState,
    answers: list[UserQuestionAnswer],
    asked: Sequence[CardQuestion] = (),
    *,
    sheets: Mapping[str, Sequence[ParameterInfo]],
) -> None:
    """Apply what each picked option binds, with no model in between.

    A value binds and a withdrawal retires; typed words and the note, never an
    offered label, become a requirement on the dimension ``asked`` names. That
    requirement replaces each one a question that asks for a stand-in names.
    """
    domain = state.domain
    recorded = {q.question: q for q in domain.open_questions}
    dimensions = {q.prompt: q.dimension for q in asked}
    labels = {q.prompt: {o.label for o in q.options} for q in asked}
    choices = requirement_choices(domain.requirements)
    for answer in answers:
        question = recorded.get(answer.prompt)
        options = {o.label: o for o in question.options} if question else choices
        words: list[str] = []
        domain.record_request_text(answer.note)
        for label in answer.chosen_labels:
            option = options.get(label)
            if option is None:
                if label not in labels.get(answer.prompt, set()):
                    domain.record_request_text(label)
                    words.append(label)
                continue
            match option.binding:
                case SetValues() as values:
                    if domain.operational_spec is not None:
                        domain.operational_spec = spec_bound_by_card(
                            domain.operational_spec,
                            values,
                            option_id=option.id,
                            sheets=sheets,
                        )
                case Withdraw(constraint_id=key):
                    domain.withdraw(c for c in domain.requirements if c.key == key)
                case Keep():
                    continue
        dimension = (
            question.dimension
            if question is not None
            else dimensions.get(answer.prompt, ConstraintKind.OTHER)
        )
        stated = _answer_requirement(answer.prompt, words, answer.note, dimension)
        if stated is not None:
            domain.record_requirements([stated])
            domain.withdraw(
                stood_in_for(
                    domain.requirements, prompt=answer.prompt, stand_in=stated
                ),
                stand_in=stated,
            )


def _bound_criterion(option: TypedOption) -> str | None:
    match option.binding:
        case SetValues(criterion_id=criterion_id):
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
    return await sheet_params_for_searches(
        site_id=state.site_id, record_type=spec.record_type, search_names=searches
    )


def _chosen(label: str, question: OpenQuestion | None) -> str:
    """The picked label, with the values its option binds."""
    options = question.options if question is not None else []
    option = next((o for o in options if o.label == label), None)
    match option:
        case TypedOption(binding=SetValues(params=params)):
            sets = ", ".join(f'{name} to "{value}"' for name, value in params.items())
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
    which binds a value. A question of your own offers no options and is
    answered in the researcher's words, about something no parameter of the
    spec sets; or it offers 'Drop <requirement>' and 'Keep <requirement>' for
    a requirement the conversation holds.

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
    pending = state.pending_approval
    card = "" if pending is None else pending.tool_call_id
    answers = list(state.user_question_answers.get(card, []))
    asked = with_summary(
        answers,
        f"{len(questions)} questions asked",
        ctx=ctx,
    )
    answered = _format_answers(answers, state.domain.open_questions)
    if answers:
        # Their answers are new requirements, so one more frame is licensed.
        state.turn_markers.framed = False
        state.turn_markers.consulted = True
        state.turn_markers.answered_card = card
        apply_option_bindings(
            state, answers, questions, sheets=await _card_sheets(state, answers)
        )
        state.domain.answer_open_questions(answered, on_card=True)
        state.domain.record_answered(_asked(questions))
    return asked
