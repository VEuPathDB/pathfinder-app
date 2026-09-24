"""The strategy an extract stages: its texts redacted, and why each step runs
what it runs."""

from __future__ import annotations

import pytest
from assistant_core.platform.types import JSONObject
from pydantic import TypeAdapter, ValidationError
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from pathfinder.domain.strategy.step_rationale import SearchRationale
from pathfinder.domain.strategy.step_words import StepWords
from pathfinder.evals.extract import EvalExtract, ExtractedTurn
from pathfinder.evals.redaction import EMAIL_PLACEHOLDER
from pathfinder.services.eval_data.extraction import (
    extracted_strategy,
    failed_redaction,
)

_EXPORTED = "GenesByExportPrediction"
# The stored metadata as written, so no label is derived again on the read.
_STORED_WORDS = TypeAdapter(dict[str, dict[str, dict[str, object]]])


def _chosen(reason: str) -> SearchRationale:
    return SearchRationale(
        search_name=_EXPORTED,
        basis="nearest",
        term="GPI anchor",
        reason=reason,
        query="GPI anchor genes ada@example.org asked for",
        tool_call_id="call_gpi",
    )


def _stored(words: StepWords) -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(id="step_1", search_name=_EXPORTED),
        name="GPI genes for ada@example.org",
        metadata=words.model_dump(by_alias=True, mode="json"),
    )


def test_the_staged_strategy_carries_each_steps_reason_redacted() -> None:
    words = StepWords(
        criterion_texts={"step_1": "the GPI genes ada@example.org listed"},
        rationales={"step_1": _chosen("nearest to a GPI anchor, per ada@example.org")},
    )

    staged = extracted_strategy(
        record_type="transcript",
        step_count=1,
        strategy_ast=_stored(words).model_dump(by_alias=True, mode="json"),
    )

    assert staged is not None
    ast = StrategyAst.model_validate(staged.strategy_ast)
    redacted = _chosen(f"nearest to a GPI anchor, per {EMAIL_PLACEHOLDER}").model_copy(
        update={"query": f"GPI anchor genes {EMAIL_PLACEHOLDER} asked for"}
    )
    assert (
        ast.name,
        StepWords.of(ast).criterion_texts,
        staged.rationales,
    ) == (
        f"GPI genes for {EMAIL_PLACEHOLDER}",
        {"step_1": f"the GPI genes {EMAIL_PLACEHOLDER} listed"},
        {"step_1": redacted},
    )


def test_a_strategy_with_no_stored_words_stages_no_reason() -> None:
    ast = StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(id="step_1", search_name=_EXPORTED),
    )

    staged = extracted_strategy(
        record_type="transcript",
        step_count=1,
        strategy_ast=ast.model_dump(by_alias=True, mode="json"),
    )

    assert staged is not None
    assert (staged.rationales, staged.strategy_ast["metadata"]) == ({}, None)


def test_the_stored_label_of_a_reason_is_redacted_with_its_term() -> None:
    chosen = _chosen("nearest to what ada@example.org asked").model_copy(
        update={"term": "ada@example.org"}
    )
    words = StepWords(rationales={"step_1": SearchRationale.model_validate(chosen)})

    staged = extracted_strategy(
        record_type="transcript",
        step_count=1,
        strategy_ast=_stored(words).model_dump(by_alias=True, mode="json"),
    )

    assert staged is not None
    stored = _STORED_WORDS.validate_python(staged.strategy_ast["metadata"])
    assert stored["rationales"]["step_1"]["short"] == f"nearest to {EMAIL_PLACEHOLDER}"


_UNPARSED: JSONObject = {
    "recordType": "transcript",
    "name": "kinases for ada@example.org",
    "description": "send the list to ada@example.org",
    "root": {"id": "step_a"},
}


def test_a_stored_strategy_that_does_not_parse_is_staged_redacted() -> None:
    staged = extracted_strategy(
        record_type="transcript", step_count=1, strategy_ast=_UNPARSED
    )

    assert staged is not None
    assert staged.strategy_ast["name"] == f"kinases for {EMAIL_PLACEHOLDER}"
    assert staged.strategy_ast["description"] == f"send the list to {EMAIL_PLACEHOLDER}"
    assert staged.strategy_ast["root"] == {"id": "step_a"}
    assert staged.structure == ""


def test_a_stored_strategy_whose_texts_cannot_be_read_stages_no_strategy() -> None:
    unread: JSONObject = {
        **_UNPARSED,
        "metadata": {"criterionTexts": ["not a mapping"]},
    }

    staged = extracted_strategy(
        record_type="transcript", step_count=1, strategy_ast=unread
    )
    readable = extracted_strategy(
        record_type="transcript", step_count=1, strategy_ast=_UNPARSED
    )

    assert staged is None
    assert readable is not None
    assert readable.step_count == 1


def test_a_refused_extract_is_read_as_a_redaction_failure() -> None:
    with pytest.raises(ValidationError) as refused:
        EvalExtract(
            site_id="plasmodb",
            assistant_id="pathfinder",
            turns=[ExtractedTurn(request="send it to ada@example.org")],
        )
    with pytest.raises(ValidationError) as malformed:
        EvalExtract.model_validate({"siteId": "plasmodb"})

    assert failed_redaction(refused.value) is True
    assert failed_redaction(malformed.value) is False
