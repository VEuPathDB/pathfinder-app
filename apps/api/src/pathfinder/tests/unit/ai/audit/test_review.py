from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from assistant_core.models.scripted import retry_prompt_parts, terminal_call
from assistant_core.models.settings import build_model_settings
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.settings import ModelSettings
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.usage import RunUsage

from pathfinder.ai.audit import review
from pathfinder.ai.audit.mock import build_review_mock
from pathfinder.ai.audit.retrievals import AuditRetrievalToolset
from pathfinder.ai.audit.review import (
    NOT_SEARCHED,
    OUT_OF_LIMITS,
    OUT_OF_RETRIES,
    review_deps,
    review_finding,
    review_settings,
)
from pathfinder.domain.audit.check_facts import evidence_facts
from pathfinder.domain.audit.findings import RelativesEvidence
from pathfinder.domain.audit.scope import SingleGeneTarget
from pathfinder.domain.audit.verdicts import FindingReview, evidence_cite, finding_cite
from pathfinder.platform.tiers import PhaseTierConfig
from pathfinder.services.audit.finding_views import (
    EvidenceView,
    FindingDetail,
    FindingView,
)
from pathfinder.services.audit.reviews import ReviewedRun

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


def _detail(finding_id: int = 7) -> FindingDetail:
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


def test_a_review_holds_the_finding_and_its_stored_evidence_only() -> None:
    deps = review_deps(_run(), _detail(), None)

    assert deps.held_reads() == frozenset(
        {finding_cite(7), evidence_cite(7, "relatives")}
    )
    assert (deps.origin, deps.genes) == ("review", frozenset({_GENE}))


async def test_a_review_naming_a_source_it_did_not_retrieve_is_retried() -> None:
    retries: list[RetryPromptPart] = []
    model = _first_then(_review(alreadyKnown="known", knownFrom=[_DOI]), retries)

    found, _ = await _reviewed(model)

    assert _DOI in str(retries[0].content)
    assert (found.already_known, found.known_from) == ("not_searched", ())


async def test_a_verdict_on_a_gene_outside_the_target_is_retried() -> None:
    retries: list[RetryPromptPart] = []
    model = _first_then(_review(verdict={"genes": ["EXA_0009"]}), retries)

    found, _ = await _reviewed(model)

    assert "EXA_0009" in str(retries[0].content)
    assert found.verdict.genes == (_GENE,)


async def test_a_review_with_no_source_open_says_not_searched() -> None:
    retries: list[RetryPromptPart] = []
    model = _first_then(_review(alreadyKnown="not_found"), retries)

    found, _ = await _reviewed(model)

    assert retries[0].content == NOT_SEARCHED
    assert found.already_known == "not_searched"


async def test_a_review_whose_retries_are_spent_is_stored_stopped() -> None:
    def answer_malformed(
        messages: list[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        del messages, info
        return ModelResponse(parts=[terminal_call({"verdict": {}})])

    found, usage = await _reviewed(FunctionModel(answer_malformed))

    assert (found.stopped, found.verdict.verdict) == (True, "undecided")
    assert (found.card_text, found.verdict.cause) == (OUT_OF_RETRIES, OUT_OF_RETRIES)
    assert found.verdict.cites == (finding_cite(7),)
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
