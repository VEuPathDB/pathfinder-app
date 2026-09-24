"""A stored analysis kind that does not parse is absent, and the rest of the
step's words still load."""

from __future__ import annotations

import pytest
from veupathdb import JSONObject, JSONValue
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.step_words import StampedKind, StepWords

_SEARCH = "GenesByRNASeqpfal3D7_Pfal3D7_Febrile_temps_RNASeq_ebi_rnaSeq_RSRCDESeq"
_KEPT = StampedKind(search_name=_SEARCH, kind=AnalysisKind.COMPUTE)


def _ast(entry: JSONValue) -> StrategyAst:
    kinds: JSONObject = {
        "step_de": entry,
        "step_ok": _KEPT.model_dump(by_alias=True, mode="json"),
    }
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="step_de",
            search_name=_SEARCH,
            parameters={"eda_dataset_id": StringValue(value="DS_e973eadd57")},
        ),
        metadata={
            "criterionTexts": {"step_de": "DE genes"},
            "analysisKinds": kinds,
        },
    )


@pytest.mark.parametrize(
    "entry",
    [
        "compute",
        {"searchName": _SEARCH, "kind": "no-such-kind"},
        {"kind": "compute"},
    ],
    ids=["bare-kind", "unknown-kind", "no-search"],
)
def test_an_entry_that_does_not_parse_is_absent(entry: JSONValue) -> None:
    words = StepWords.of(_ast(entry))

    assert (words.criterion_texts, words.analysis_kinds) == (
        {"step_de": "DE genes"},
        {"step_ok": _KEPT},
    )
