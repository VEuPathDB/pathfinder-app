from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from strategist.domain.audit.verdicts import GeneModelVerdict, VerdictKind
from strategist.evals.case import CaseProvenance, EvalCase, ExpectedOutcome, GatePlan
from strategist.evals.difference import CaseDifference
from strategist.evals.redaction import RedactionFailedError
from strategist.evals.run_directory import score_run_directory
from strategist.evals.scoring import ObservedOutcome, score_case
from strategist.evals.store import load_case
from strategist.evals.verdict_scoring import (
    ObservedVerdict,
    newest_verdicts,
    verdict_differences,
)
from strategist.services.audit.verdicts import VerdictView

_RUN = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "evals"
    / "run_directory"
    / "orthomcl-one-protein-in-each-cryptosporidium-genome"
)
_GENE = "EXA_0001"


def _expected(**fields: object) -> ExpectedOutcome:
    return ExpectedOutcome.model_validate({"buildsStrategy": False, **fields})


def _case(expected: ExpectedOutcome) -> EvalCase:
    return EvalCase(
        name="an-audit-case",
        turns=["check this gene model"],
        site_id="plasmodb",
        assistant_id="audit",
        rationale="pins a stored verdict",
        expected=expected,
        gates=GatePlan(policy="leave"),
        provenance=CaseProvenance(
            site="plasmodb",
            assistant="audit",
            origin="cataloged-failure",
            reference="a-design.md",
            added_at="2026-11-10",
        ),
    )


def _observed(kind: VerdictKind, cause: str) -> dict[str, ObservedVerdict]:
    return {
        _GENE: ObservedVerdict(
            verdict=kind,
            error_type="truncated_model" if kind == "error" else None,
            cause=cause,
        )
    }


def _view(view_id: int, kind: VerdictKind, cause: str, hour: int) -> VerdictView:
    error = kind == "error"
    return VerdictView(
        id=view_id,
        run_id=None,
        finding_id=None,
        origin="auditor",
        verdict=GeneModelVerdict(
            genes=(_GENE,),
            model_genome="Examplea alpha A",
            verdict=kind,
            error_type="truncated_model" if error else None,
            certainty="high" if error else None,
            cause=cause,
            cites=("read_gene_model:EXA_0001",),
        ),
        review=None,
        created_at=datetime(2026, 11, 10, hour, tzinfo=UTC),
    )


def test_a_kept_error_with_its_cause_passes() -> None:
    expected = _expected(
        verdicts={_GENE: "error"}, verdictCauses={_GENE: ["open frame"]}
    )

    differences = verdict_differences(
        expected, _observed("error", "the genome encodes one open frame")
    )

    assert differences == []


def test_a_no_error_verdict_fails_by_gene() -> None:
    expected = _expected(verdicts={_GENE: "error"})

    differences = verdict_differences(
        expected, _observed("no_error", "the model is whole")
    )

    assert differences == [
        CaseDifference(field="verdicts.EXA_0001", expected="error", actual="no_error")
    ]


def test_a_missing_gene_fails_as_none() -> None:
    expected = _expected(verdicts={_GENE: "error"})

    differences = verdict_differences(expected, {})

    assert differences == [
        CaseDifference(field="verdicts.EXA_0001", expected="error", actual="(none)")
    ]


def test_a_missing_cause_phrase_fails() -> None:
    expected = _expected(
        verdicts={_GENE: "error"},
        verdictCauses={_GENE: ["Open Frame", "stop codon"]},
    )

    differences = verdict_differences(
        expected, _observed("error", "the genome encodes one open frame")
    )

    assert differences == [
        CaseDifference(
            field="verdictCauses.EXA_0001",
            expected="stop codon",
            actual="the genome encodes one open frame",
        )
    ]


def test_the_newest_verdict_names_the_gene() -> None:
    views = [
        _view(2, "no_error", "the model is whole", 12),
        _view(1, "error", "the model stops early", 9),
    ]

    newest = newest_verdicts(views)

    assert newest == {
        _GENE: ObservedVerdict(
            verdict="no_error", error_type=None, cause="the model is whole"
        )
    }


def test_a_cause_for_an_unexpected_gene_is_refused() -> None:
    with pytest.raises(ValidationError, match="EXA_0002"):
        _expected(verdicts={_GENE: "error"}, verdictCauses={"EXA_0002": ["frame"]})


def test_a_cause_phrase_is_de_identified() -> None:
    case = _case(
        _expected(
            verdicts={_GENE: "error"},
            verdictCauses={_GENE: ["ask curator@example.org"]},
        )
    )

    with pytest.raises(RedactionFailedError, match="email"):
        case.assert_de_identified()


def test_a_case_scores_its_verdicts() -> None:
    case = _case(_expected(verdicts={_GENE: "error"}))

    score = score_case(
        case,
        ObservedOutcome(
            built_strategy=False, verdicts=_observed("no_error", "the model is whole")
        ),
    )

    assert (score.passed, [d.field for d in score.differences]) == (
        False,
        ["verdicts.EXA_0001"],
    )


def test_a_directory_run_expecting_verdicts_fails() -> None:
    measured = load_case("orthomcl-one-protein-in-each-cryptosporidium-genome")
    case = measured.model_copy(
        update={
            "expected": measured.expected.model_copy(
                update={"verdicts": {_GENE: "error", "EXA_0002": "no_error"}}
            )
        }
    )

    result = score_run_directory(case, _RUN, None, "8.2")

    assert [
        (d.field, d.actual)
        for d in result.differences
        if d.field.startswith("verdicts.")
    ] == [("verdicts.EXA_0001", "(none)"), ("verdicts.EXA_0002", "(none)")]
