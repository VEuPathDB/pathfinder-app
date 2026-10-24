from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from assistant_core.models.scripted import retry_prompt_parts, terminal_call
from assistant_core.models.settings import build_model_settings
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.settings import ModelSettings
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.usage import RunUsage

from pathfinder.ai.audit import review
from pathfinder.ai.audit.instructions import LITERATURE_INSTRUCTIONS
from pathfinder.ai.audit.mock import build_review_mock
from pathfinder.ai.audit.retrievals import AuditRetrievalToolset
from pathfinder.ai.audit.review import (
    OUT_OF_LIMITS,
    OUT_OF_RETRIES,
    review_deps,
    review_finding,
    review_settings,
)
from pathfinder.domain.audit.check_facts import evidence_facts
from pathfinder.domain.audit.findings import RelativesEvidence
from pathfinder.domain.audit.models import FindingModels
from pathfinder.domain.audit.scope import SingleGeneTarget
from pathfinder.domain.audit.verdicts import FindingReview, evidence_cite, finding_cite
from pathfinder.platform.tiers import PhaseTierConfig
from pathfinder.services.audit.finding_views import (
    EvidenceView,
    FindingDetail,
    FindingView,
)
from pathfinder.services.audit.reviews import ReviewedRun
from pathfinder.tests._support.audit_answers import PKAC_STRAIN_MODELS

_GENOME = "Examplea alpha A"
_GENE = "EXA_0001"
_DOI = "10.1000/example.1"
_RELATIVES = RelativesEvidence(
    reference_gene="EXB_0001",
    reference_length=400,
    model_length=200,
    relatives_median=400.0,
    relative_lengths={},
    relatives_tier=None,
    side=None,
    reference_organism=None,
)


def _detail(finding_id: int = 7, models: FindingModels | None = None) -> FindingDetail:
    return FindingDetail(
        site_id="plasmodb",
        finding=FindingView(
            id=finding_id,
            genome=_GENOME,
            screened_genome=_GENOME,
            paired_genome=None,
            target=SingleGeneTarget(check="gene_length", genes=(_GENE,)),
            sampled=True,
            status="confirmed",
            error_type="truncated_model",
            certainty="high",
            judged=True,
            impact=1.0,
            weighing=None,
            requests=2,
            attempts=1,
            stopped=0,
            message=None,
            reviewed=False,
            verdict=None,
            from_target=True,
            review_line=None,
            genes=[],
        ),
        evidence=[
            EvidenceView(
                kind="relatives",
                status="stored",
                payload=_RELATIVES,
                requests=1,
                attempts=1,
                stopped=0,
                message=None,
            ),
            EvidenceView(
                kind="gene_evidence",
                status="failed",
                payload=None,
                requests=1,
                attempts=1,
                stopped=0,
                message="the site refused the read",
            ),
        ],
        facts=[evidence_facts(_RELATIVES)],
        review=None,
        review_text=None,
        genes=[],
        models=models,
    )


def _run() -> ReviewedRun:
    return ReviewedRun(
        run_id=uuid4(),
        user_id=uuid4(),
        conversation_id=uuid4(),
        site_id="plasmodb",
        status="finished",
        seed=11,
        review=None,
        named=1,
    )


def _review(**changed: Any) -> dict[str, Any]:
    return {
        "verdict": {
            "genes": [_GENE],
            "modelGenome": _GENOME,
            "verdict": "error",
            "errorType": "truncated_model",
            "certainty": "high",
            "cause": "The relatives are longer.",
            "cites": [finding_cite(7)],
            **changed.pop("verdict", {}),
        },
        "alreadyKnown": "not_searched",
        "cardText": "A truncated synthetic model.",
        **changed,
    }


def _first_then(wrong: dict[str, Any], retries: list[RetryPromptPart]) -> FunctionModel:
    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        retries.extend(retry_prompt_parts(messages))
        return ModelResponse(parts=[terminal_call(_review() if retries else wrong)])

    return FunctionModel(answer)


async def _reviewed(
    model: Model,
    research: AbstractToolset[Any] | None = None,
    settings: ModelSettings | None = None,
) -> tuple[FindingReview, RunUsage]:
    usage = RunUsage()
    found = await review_finding(
        _detail(),
        deps=review_deps(_run(), _detail(), research),
        model=model,
        settings=settings,
        usage=usage,
    )
    return found, usage


async def test_the_review_prompt_holds_no_models() -> None:
    annotated = tuple(model for model in PKAC_STRAIN_MODELS if model is not None)
    detail = _detail(models=FindingModels(kind="strain", annotated=annotated))
    prompts: list[str] = []

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        match messages[0]:
            case ModelRequest(parts=[*_, UserPromptPart(content=str() as prompt)]):
                prompts.append(prompt)
            case _:
                pass
        return ModelResponse(parts=[terminal_call(_review())])

    await review_finding(
        detail,
        deps=review_deps(_run(), detail, None),
        model=FunctionModel(answer),
        settings=None,
        usage=RunUsage(),
    )

    assert prompts == [detail.model_dump_json(by_alias=True, exclude={"models"})]
    assert '"models"' not in prompts[0]
    assert '"facts"' in prompts[0]


def test_a_review_holds_the_finding_and_its_stored_evidence_only() -> None:
    deps = review_deps(_run(), _detail(), None)

    assert deps.held_reads() == frozenset(
        {finding_cite(7), evidence_cite(7, "relatives")}
    )
    assert (deps.origin, deps.genes) == ("review", frozenset({_GENE}))


async def test_a_review_naming_a_source_it_did_not_retrieve_is_retried() -> None:
    retries: list[RetryPromptPart] = []
    model = _first_then(_review(alreadyKnown="known", knownFrom=[_DOI]), retries)
    research = AuditRetrievalToolset(
        FunctionToolset([literature_search]).prefixed("research")
    )

    found, _ = await _reviewed(model, research)

    assert _DOI in str(retries[0].content)
    assert (found.already_known, found.known_from) == ("not_searched", ())


async def test_a_verdict_on_a_gene_outside_the_target_is_retried() -> None:
    retries: list[RetryPromptPart] = []
    model = _first_then(_review(verdict={"genes": ["EXA_0009"]}), retries)

    found, _ = await _reviewed(model)

    assert "EXA_0009" in str(retries[0].content)
    assert found.verdict.genes == (_GENE,)


def _offered(seen: list[tuple[list[str], str | None]]) -> FunctionModel:
    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        (output,) = info.output_tools
        seen.append(
            (list(output.parameters_json_schema["properties"]), info.instructions)
        )
        return ModelResponse(parts=[terminal_call(_review())])

    return FunctionModel(answer)


async def test_a_review_with_no_source_open_is_offered_no_literature_field() -> None:
    seen: list[tuple[list[str], str | None]] = []

    found, _ = await _reviewed(_offered(seen))

    ((fields, instructions),) = seen
    assert fields == [
        "verdict",
        "cardText",
        "impact",
        "impactReason",
        "secondVerdict",
        "stopped",
    ]
    assert instructions is not None
    assert "literature" not in instructions
    assert "already known" not in instructions
    assert (found.already_known, found.known_from, found.paper_depends) == (
        "not_searched",
        (),
        None,
    )


async def test_a_review_with_a_source_open_is_offered_the_literature_fields() -> None:
    seen: list[tuple[list[str], str | None]] = []
    research = AuditRetrievalToolset(
        FunctionToolset([literature_search]).prefixed("research")
    )

    await _reviewed(_offered(seen), research)

    ((fields, instructions),) = seen
    assert fields == [
        "verdict",
        "alreadyKnown",
        "knownFrom",
        "paperDepends",
        "cardText",
        "impact",
        "impactReason",
        "secondVerdict",
        "stopped",
    ]
    assert instructions is not None
    assert instructions.endswith(LITERATURE_INSTRUCTIONS.strip())


async def test_a_review_claiming_known_with_no_source_open_is_refused() -> None:
    retries: list[RetryPromptPart] = []
    model = _first_then(
        _review(alreadyKnown="known", knownFrom=[finding_cite(7)]), retries
    )

    found, _ = await _reviewed(model)

    match retries[0].content:
        case str() as refusal:
            pytest.fail(refusal)
        case errors:
            refused = [(e["loc"], e["msg"]) for e in errors]
    unsearched = (
        "Value error, no literature source is open for this review, so it "
        "states nothing about the literature"
    )
    assert refused == [((), unsearched)]
    assert found.already_known == "not_searched"


async def test_a_review_whose_retries_are_spent_stores_its_last_refusal() -> None:
    def answer_malformed(
        messages: list[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        del messages, info
        return ModelResponse(parts=[terminal_call({"verdict": {}})])

    found, usage = await _reviewed(FunctionModel(answer_malformed))

    reason = (
        f"{OUT_OF_RETRIES} The last refusal: verdict.genes: Field required; "
        "verdict.modelGenome: Field required; verdict.verdict: Field required; "
        "verdict.cause: Field required; verdict.cites: Field required; "
        "cardText: Field required"
    )
    assert (found.stopped, found.verdict.verdict) == (True, "undecided")
    assert (found.card_text, found.verdict.cause) == (reason, reason)
    assert found.verdict.cites == (finding_cite(7),)
    assert usage.requests == 4


def _always(answer: dict[str, Any]) -> FunctionModel:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        return ModelResponse(parts=[terminal_call(answer)])

    return FunctionModel(respond)


async def test_a_review_its_validator_refuses_to_the_end_stores_that_refusal() -> None:
    model = _always(_review(verdict={"genes": ["EXA_0009"]}))

    found, usage = await _reviewed(model)

    assert found.verdict.cause == (
        f"{OUT_OF_RETRIES} The last refusal: These genes are not the finding's: "
        "EXA_0009. Judge only the genes of its target: EXA_0001."
    )
    assert usage.requests == 4


async def test_a_review_that_keeps_claiming_known_stores_why_it_was_refused() -> None:
    model = _always(_review(alreadyKnown="known", knownFrom=[finding_cite(7)]))

    found, usage = await _reviewed(model)

    assert found.verdict.cause == (
        f"{OUT_OF_RETRIES} The last refusal: Value error, no literature source "
        "is open for this review, so it states nothing about the literature"
    )
    assert usage.requests == 4


def search_forever(query: str) -> dict[str, Any]:
    del query
    return {"results": []}


async def test_a_review_at_its_limit_is_stored_stopped_for_that_cause() -> None:
    def keep_searching(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        call = ToolCallPart(tool_name="research_search_forever", args={"query": "x"})
        return ModelResponse(parts=[call])

    research = AuditRetrievalToolset(
        FunctionToolset([search_forever]).prefixed("research")
    )

    found, _ = await _reviewed(FunctionModel(keep_searching), research)

    assert (found.stopped, found.card_text) == (True, OUT_OF_LIMITS)


async def test_the_reviewer_runs_on_the_settings_it_is_given() -> None:
    seen: list[ModelSettings | None] = []

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        seen.append(info.model_settings)
        return ModelResponse(parts=[terminal_call(_review())])

    settings = ModelSettings(max_tokens=321)
    await _reviewed(FunctionModel(answer), settings=settings)

    assert seen == [settings]


def test_the_review_settings_carry_the_review_roles_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PhaseTierConfig(model_id="openai:gpt-5.6-luna", reasoning_effort="high")
    asked: list[tuple[str, str]] = []

    def role_config(assistant_id: str, role: str) -> PhaseTierConfig:
        asked.append((assistant_id, role))
        return config

    monkeypatch.setattr(review, "deployment_role_config", role_config)

    settings = review_settings("openai:gpt-5.6-luna")

    assert settings == build_model_settings("openai:gpt-5.6-luna", thinking="high")
    assert asked == [("audit", "audit_review")]


def literature_search(query: str) -> dict[str, Any]:
    del query
    return {"results": [{"doi": _DOI}]}


async def test_the_mock_reviewer_names_what_its_search_retrieved() -> None:
    research = AuditRetrievalToolset(
        FunctionToolset([literature_search]).prefixed("research")
    )

    found, _ = await _reviewed(build_review_mock(), research)

    assert (found.already_known, found.known_from) == ("known", (_DOI,))
    assert found.verdict.cites == (finding_cite(7),)
    assert (found.verdict.verdict, found.verdict.error_type) == (
        "error",
        "truncated_model",
    )
