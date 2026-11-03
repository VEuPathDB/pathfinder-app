from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import get_args

import pytest
from assistant_core.errors import ModelDeclinedError
from pydantic_ai.exceptions import ContentFilterError
from pydantic_ai.messages import (
    BinaryContent,
    ModelMessage,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from veupathdb_mcp.catalog import DecisionRequest, DecisionResponse

from pathfinder.ai.capabilities.metering import SpendMeter
from pathfinder.ai.lead.message_reader import ReaderInput, read_message, reading_guide
from pathfinder.domain.message_reading import Effect, StatedRequest, Want
from pathfinder.domain.strategy.constraints import RecordTypeValue, UntypedValue

MESSAGE = "Move it to chromosome 12 and tell me the new count."
_FILTERED = "the provider filtered the request"
READ = ReaderInput(
    conversation="Researcher: Mouse genes on chromosome 17 with MHC class I.\nYou replied: 9 genes.",
    strategy="Genomic Location INTERSECT GO Term = 9 genes",
    steps=["step_7f08: Genomic Location", "step_beab: GO Term"],
    message=MESSAGE,
)
STATED = {
    "goal": "the same intersection on chromosome 12",
    "requirements": [
        {
            "quote": "chromosome 12",
            "kind": "count",
            "value": "chromosome 12",
            "feature": "chromosome",
            "op": "=",
            "number": 12,
            "hard": True,
        }
    ],
    "asks": ["tell me the new count"],
}


def _choice(
    name: str, picked: str, probability: float, others: dict[str, float] | None = None
) -> dict[str, object]:
    probabilities = [{"value": picked, "probability": probability}] + [
        {"value": k, "probability": v} for k, v in (others or {}).items()
    ]
    return {
        "type": "choice",
        "name": name,
        "choice": picked,
        "probabilities": probabilities,
        "confidence": probability,
    }


def _answer(
    effect: tuple[str, float], wants: tuple[str, float], **flags: float
) -> DecisionResponse:
    answers: list[dict[str, object]] = [
        _choice("effect", *effect),
        _choice("wants", *wants),
        _choice("edit_direction", "other", 0.9),
    ] + [{"type": "predicate", "name": k, "probability": v} for k, v in flags.items()]
    return DecisionResponse.model_validate(
        {"answers": answers, "usage": {"input_tokens": 900}}
    )


class _Decisions:
    def __init__(self, *answers: DecisionResponse | None) -> None:
        self.answers = list(answers)
        self.asked: list[DecisionRequest] = []

    async def __call__(self, request: DecisionRequest) -> DecisionResponse | None:
        self.asked.append(request)
        return self.answers.pop(0)


_UNREAD = {"effect": "none", "wants": "nothing"}


class _Model:
    def __init__(self, *outputs: Mapping[str, object]) -> None:
        self.stated = [o for o in outputs if "effect" not in o]
        self.readings = [o for o in outputs if "effect" in o]
        self.prompts: list[str] = []
        self.read_prompts: list[str] = []
        self.files: list[list[BinaryContent]] = []

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        [content] = [
            p.content
            for m in messages
            for p in m.parts
            if isinstance(p, UserPromptPart)
        ]
        parts = [content] if isinstance(content, str) else list(content)
        prompt = "\n\n".join(c for c in parts if isinstance(c, str))
        self.files.append([c for c in parts if isinstance(c, BinaryContent)])
        output = info.output_tools[0]
        if "effect" in output.parameters_json_schema["properties"]:
            self.read_prompts.append(prompt)
            args = self.readings.pop(0) if self.readings else _UNREAD
        else:
            self.prompts.append(prompt)
            args = self.stated.pop(0)
        return ModelResponse(
            parts=[ToolCallPart(tool_name=output.name, args=dict(args))]
        )


def _request_model(*outputs: Mapping[str, object]) -> tuple[FunctionModel, _Model]:
    script = _Model(*outputs)
    return FunctionModel(script), script


def test_the_guide_defines_every_effect_want_and_flag_once() -> None:
    guide = reading_guide()

    assert sorted(guide.effects) == sorted(get_args(Effect.__value__))
    assert sorted(guide.wants) == sorted(get_args(Want.__value__))
    assert sorted(guide.flags) == sorted(
        [
            "answers_open_question",
            "sets_aside_open_question",
            "disputes_result",
            "audit",
            "remember",
            "context_only",
            "off_topic",
        ]
    )


async def test_a_settled_decision_reads_the_message_and_the_model_states_the_request() -> (
    None
):
    ask = _Decisions(
        _answer(("change", 0.95), ("status", 0.9)),
        _answer(("change", 0.93), ("status", 0.88)),
    )
    model, script = _request_model(STATED)
    meter = SpendMeter()

    reading, stated = await read_message(
        READ, model=model, model_id="openai:gpt-5.6-luna", meter=meter, ask=ask
    )

    assert (reading.effect, reading.wants, reading.read_by) == (
        "change",
        "status",
        "decisions",
    )
    assert stated == StatedRequest.model_validate(STATED)
    assert len(script.prompts) == 1
    assert len(ask.asked) == 2
    assert [q.name for q in ask.asked[0].questions] == [
        "effect",
        "wants",
        "edit_direction",
        "disputes_result",
        "audit",
        "remember",
        "context_only",
        "off_topic",
    ]
    assert len(meter.spent) == len(script.prompts) + len(script.read_prompts)


async def test_an_unsure_decision_leaves_effect_and_wants_to_the_model() -> None:
    ask = _Decisions(
        _answer(("none", 0.45), ("status", 0.5), disputes_result=0.9), None
    )
    model, script = _request_model(STATED, {"effect": "change", "wants": "status"})

    reading, _ = await read_message(
        READ, model=model, model_id="openai:gpt-5.6-luna", meter=SpendMeter(), ask=ask
    )

    assert (
        reading.effect,
        reading.wants,
        reading.read_by,
        reading.disputes_result,
    ) == ("change", "status", "model", True)
    assert (len(script.prompts), len(script.read_prompts)) == (1, 1)


async def test_with_no_decision_the_model_reads_the_whole_message() -> None:
    ask = _Decisions(None, None)
    model, _ = _request_model(
        STATED, {"effect": "change", "wants": "status", "off_topic": False}
    )

    reading, _ = await read_message(
        READ, model=model, model_id="openai:gpt-5.6-luna", meter=SpendMeter(), ask=ask
    )

    assert (reading.effect, reading.read_by) == ("change", "model")


async def test_an_open_question_is_asked_about_and_otherwise_never_answered() -> None:
    opened = READ.model_copy(update={"question_open": True})
    ask = _Decisions(
        _answer(("change", 0.95), ("nothing", 0.95), answers_open=0.9), None
    )
    model, _ = _request_model(STATED)

    reading, _ = await read_message(
        opened, model=model, model_id="openai:gpt-5.6-luna", meter=SpendMeter(), ask=ask
    )

    assert reading.answers_open is True
    assert ask.asked[0].questions[-1].name == "answers_open"


async def test_a_quote_the_message_does_not_hold_is_asked_once_more_then_dropped() -> (
    None
):
    wrong = {
        **STATED,
        "requirements": [
            {
                "quote": "chromosome twelve",
                "kind": "count",
                "value": "chromosome 12",
                "feature": "chromosome",
                "op": "=",
                "number": 12,
            }
        ],
    }
    ask = _Decisions(_answer(("change", 0.95), ("status", 0.9)), None)
    model, script = _request_model(wrong, wrong)

    _, stated = await read_message(
        READ, model=model, model_id="openai:gpt-5.6-luna", meter=SpendMeter(), ask=ask
    )

    assert stated.requirements == []
    assert len(script.prompts) == 2
    assert '"chromosome twelve"' in script.prompts[1]


async def test_a_corrected_quote_is_kept() -> None:
    wrong = {
        **STATED,
        "requirements": [
            {
                "quote": "chromosome twelve",
                "kind": "count",
                "value": "chromosome 12",
                "feature": "chromosome",
                "op": "=",
                "number": 12,
            }
        ],
    }
    ask = _Decisions(_answer(("change", 0.95), ("status", 0.9)), None)
    model, _ = _request_model(wrong, STATED)

    _, stated = await read_message(
        READ, model=model, model_id="openai:gpt-5.6-luna", meter=SpendMeter(), ask=ask
    )

    assert [r.quote for r in stated.requirements] == ["chromosome 12"]


@pytest.mark.parametrize("latest_first", [0, 1])
async def test_both_views_carry_the_latest_message(latest_first: int) -> None:
    ask = _Decisions(
        _answer(("change", 0.95), ("status", 0.9)),
        _answer(("change", 0.9), ("status", 0.9)),
    )
    model, _ = _request_model(STATED)

    await read_message(
        READ, model=model, model_id="openai:gpt-5.6-luna", meter=SpendMeter(), ask=ask
    )

    view = ask.asked[latest_first].input
    assert MESSAGE in view
    assert (
        view.index(MESSAGE) < view.index("## The strategy now")
        if latest_first
        else view.index(MESSAGE) > view.index("## The strategy now")
    )


async def test_the_files_of_the_message_reach_every_model_call() -> None:
    gene_list = BinaryContent(data=b"PF3D7_1133400\n", media_type="text/plain")
    with_file = READ.model_copy(update={"files": ["genes.txt"]})
    ask = _Decisions(_answer(("none", 0.4), ("status", 0.4)), None)
    model, script = _request_model(STATED, {"effect": "add", "wants": "nothing"})

    await read_message(
        with_file,
        files=[gene_list],
        model=model,
        model_id="openai:gpt-5.6-luna",
        meter=SpendMeter(),
        ask=ask,
    )

    assert script.files == [[gene_list]] * 2
    assert "genes.txt" in ask.asked[0].input


class _SlowDecisions(_Decisions):
    def __init__(self, order: list[str], *answers: DecisionResponse | None) -> None:
        super().__init__(*answers)
        self.order = order

    async def __call__(self, request: DecisionRequest) -> DecisionResponse | None:
        await asyncio.sleep(0.05)
        self.order.append("decided")
        return await super().__call__(request)


async def test_the_model_reading_starts_before_the_decision_answers() -> None:
    order: list[str] = []
    ask = _SlowDecisions(order, _answer(("none", 0.4), ("status", 0.4)), None)
    script = _Model(STATED, {"effect": "add", "wants": "nothing"})

    def _recorded(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "effect" in info.output_tools[0].parameters_json_schema["properties"]:
            order.append("modeled")
        return script(messages, info)

    reading, _ = await read_message(
        READ,
        model=FunctionModel(_recorded),
        model_id="openai:gpt-5.6-luna",
        meter=SpendMeter(),
        ask=ask,
    )

    assert order.index("modeled") < order.index("decided")
    assert (reading.effect, reading.read_by) == ("add", "model")


HELD = READ.model_copy(
    update={"held": {"R1": "organism: Mus musculus", "R2": "count: chromosome 17"}}
)


async def test_only_the_extraction_reads_the_numbered_held_requirements() -> None:
    ask = _Decisions(_answer(("change", 0.95), ("status", 0.9)), None)
    model, script = _request_model(STATED)

    await read_message(
        HELD, model=model, model_id="openai:gpt-5.6-luna", meter=SpendMeter(), ask=ask
    )

    listed = "## The requirements the conversation holds\nR1: organism: Mus musculus\nR2: count: chromosome 17"
    assert (listed in script.prompts[0], [listed in a.input for a in ask.asked]) == (
        True,
        [False, False],
    )


async def test_a_withdrawal_names_a_held_number_or_is_dropped() -> None:
    taking_back = {
        **STATED,
        "withdrawn": [
            {"quote": "Move it to chromosome 12", "requirement": "R2"},
            {"quote": "Move it", "requirement": "R7"},
            {"quote": "chromosome 12", "requirement": ""},
        ],
    }
    ask = _Decisions(_answer(("change", 0.95), ("status", 0.9)), None)
    model, _ = _request_model(taking_back)

    _, stated = await read_message(
        HELD, model=model, model_id="openai:gpt-5.6-luna", meter=SpendMeter(), ask=ask
    )

    assert [(w.quote, w.requirement) for w in stated.withdrawn] == [
        ("Move it to chromosome 12", "R2")
    ]


async def test_a_thread_that_holds_nothing_lists_no_requirements() -> None:
    ask = _Decisions(_answer(("change", 0.95), ("status", 0.9)), None)
    model, script = _request_model(STATED)

    await read_message(
        READ, model=model, model_id="openai:gpt-5.6-luna", meter=SpendMeter(), ask=ask
    )

    assert "## The requirements the conversation holds" not in script.prompts[0]


ORTHOMCL = READ.model_copy(
    update={
        "message": "Take the ortholog groups, keep their 3D7 proteins, then list the pathways.",
        "record_classes": {"group": "Ortholog Groups", "sequence": "Proteins"},
    }
)


def _record_type(quote: str, record_class: str, role: str) -> dict[str, object]:
    return {
        "quote": quote,
        "kind": "record_type",
        "value": quote,
        "recordClass": record_class,
        "role": role,
    }


async def test_only_the_extraction_reads_the_record_classes_the_site_lists() -> None:
    ask = _Decisions(_answer(("new", 0.95), ("show_records", 0.9)), None)
    model, script = _request_model({"requirements": []})

    await read_message(
        ORTHOMCL,
        model=model,
        model_id="openai:gpt-5.6-luna",
        meter=SpendMeter(),
        ask=ask,
    )

    listed = "## The record classes the site lists\n- group: Ortholog Groups\n- sequence: Proteins"
    assert (listed in script.prompts[0], [listed in a.input for a in ask.asked]) == (
        True,
        [False, False],
    )


async def test_a_record_class_the_site_does_not_list_is_untyped() -> None:
    stated = {
        "requirements": [
            _record_type("ortholog groups", "group", "answer"),
            _record_type("3D7 proteins", "sequence", "through"),
            _record_type("pathways", "pathway", "answer"),
        ]
    }
    ask = _Decisions(_answer(("new", 0.95), ("show_records", 0.9)), None)
    model, _ = _request_model(stated)

    _, request = await read_message(
        ORTHOMCL,
        model=model,
        model_id="openai:gpt-5.6-luna",
        meter=SpendMeter(),
        ask=ask,
    )

    assert [(r.kind, r.quote, r.typed()) for r in request.requirements] == [
        ("record_type", "ortholog groups", RecordTypeValue(record_class="group")),
        (
            "record_type",
            "3D7 proteins",
            RecordTypeValue(record_class="sequence", role="through"),
        ),
        ("untyped", "pathways", UntypedValue(text="pathways")),
    ]


async def test_a_reading_the_provider_filters_is_declined() -> None:
    def _filtered(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        raise ContentFilterError(_FILTERED)

    with pytest.raises(ModelDeclinedError):
        await read_message(
            READ,
            model=FunctionModel(_filtered),
            model_id="openai:gpt-5.6-luna",
            meter=SpendMeter(),
            ask=_Decisions(None, None),
        )
