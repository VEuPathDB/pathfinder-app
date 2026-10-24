"""The Lead's audit replies of a recorded run render as single prose, with no stored value written twice or raw."""

from __future__ import annotations

from pydantic import BaseModel, JsonValue
from veupathdb_mcp.audit import IntronAudit

from pathfinder.domain.record_facts import SourceFact
from pathfinder.domain.reply_references import prose_faults, render_reply
from pathfinder.domain.statistic_facts import StatisticFact, StatisticKind
from pathfinder.domain.statistic_rows import schema_rows
from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.services.audit.finding_views import FindingDetail
from pathfinder.services.audit.views import AuditRunView

_PLASMO = "https://qa.plasmodb.org/plasmo.qa/app/record/gene/"
_VECTOR = "https://qa.vectorbase.org/vectorbase.qa/app/record/gene/"
_FUNGI = "https://qa.fungidb.org/fungidb.qa/app/record/gene/"
_DASH = chr(0x2014)
_CAUSE = (
    "The annotated intron is unsupported by RNA-seq, whereas a nearby replacement "
    "junction is supported by 1,226 reads and preserves the coding frame. This "
    "supports a shifted splice site, but certainty remains medium because no "
    "splice motif was recorded and neither the annotated nor corrected model "
    "matched the surveyed orthologs."
)


def _fact(
    fact_id: str, kind: StatisticKind, source: type[BaseModel], answer: JsonValue
) -> StatisticFact:
    return StatisticFact(
        id=fact_id, kind=kind, title=fact_id, rows=schema_rows(source, answer)
    )


def _facts(statistics: list[StatisticFact], genes: list[str], page: str) -> TurnFacts:
    return TurnFacts(
        audit_statistics=statistics,
        sources=[SourceFact(record_id=gene, url=f"{page}{gene}") for gene in genes],
    )


def _shifted(introns: list[int], replacement: int) -> JsonValue:
    return {
        "verdict": "UNSUPPORTED_SHIFTED",
        "introns": [{"reads": reads} for reads in introns],
        "unread": [{"replacement": [{"reads": replacement}]}],
        "frameKept": True,
    }


def test_a_finding_reply_names_its_certainty_and_review_once() -> None:
    facts = _facts(
        [
            _fact(
                "stat_ad5c5b01",
                "audit_finding",
                FindingDetail,
                {
                    "finding": {
                        "id": 1,
                        "certainty": "high",
                        "verdictText": "RNA-seq reads join an exon the model does not have",
                    },
                    "review": {"verdict": {"verdict": "undecided"}},
                    "reviewText": {"literatureText": "The literature was not searched"},
                },
            )
        ],
        ["PcyM_0736700"],
        _PLASMO,
    )
    prose = (
        "For [record:PcyM_0736700], the audit found a confirmed missing-"
        "exon problem in the annotated transcript: RNA-seq junctions "
        "support an exon structure that the current model lacks, so the "
        "model is judged unsupported as annotated "
        "[stat:stat_ad5c5b01.finding.verdictText].\n\nConfidence in the "
        "underlying RNA-seq finding is high "
        "[stat:stat_ad5c5b01.finding.certainty]. However, the separate "
        "adjudication review was undecided "
        "[stat:stat_ad5c5b01.review.verdict.verdict]: it stopped before "
        "writing a valid review, and no literature check was performed "
        "[stat:stat_ad5c5b01.reviewText.literatureText]. So this is "
        "strong evidence that the current model is missing an exon, but "
        "not a completed expert adjudication of the proposed correction."
    )

    assert prose_faults(prose, facts) == []
    assert render_reply(prose, facts) == (
        f"For [PcyM_0736700]({_PLASMO}PcyM_0736700), the audit found a "
        "confirmed missing-exon problem in the annotated transcript: RNA-seq "
        "junctions support an exon structure that the current model lacks, so "
        "the model is judged unsupported as annotated[^1].\n\nConfidence in the "
        "underlying RNA-seq finding is high[^2]. However, the separate "
        "adjudication review was undecided[^3]: it stopped before writing a "
        "valid review, and no literature check was performed[^4]. So this is "
        "strong evidence that the current model is missing an exon, but not a "
        "completed expert adjudication of the proposed correction.\n\n"
        "[^1]: verdict text: RNA-seq reads join an exon the model does not have\n"
        "[^2]: certainty: high\n"
        "[^3]: verdict: undecided\n"
        "[^4]: literature text: The literature was not searched"
    )


def test_a_run_reply_names_its_certainty_and_agreement_once() -> None:
    facts = _facts(
        [
            _fact(
                "stat_c436453c",
                "audit_run",
                AuditRunView,
                {
                    "errorTypes": [{"certainty": "high"}],
                    "agreement": {
                        "text": (
                            "Two independent reviews agreed on 2 of 2 sampled "
                            "findings (100%)"
                        )
                    },
                },
            )
        ],
        ["AFAF012298"],
        _VECTOR,
    )
    prose = (
        "For [record:AFAF012298], the audit found a **missing internal "
        "exon**: RNA-seq replacement junctions support two omitted "
        "segments, and the corrected model matches independently read "
        "orthologs whereas the annotated model matches none. The finding "
        "was judged **high certainty** "
        "[stat:stat_c436453c.errorTypes.0.certainty].\n\nThe evidence "
        "review is complete, and the independent reviews agreed on every "
        "sampled finding [stat:stat_c436453c.agreement.text]. This makes "
        "the result strong enough to prioritize a model revision, while "
        "the exact exon boundaries should still be checked before "
        "updating the annotation."
    )

    assert prose_faults(prose, facts) == []
    assert render_reply(prose, facts) == (
        f"For [AFAF012298]({_VECTOR}AFAF012298), the audit found a **missing "
        "internal exon**: RNA-seq replacement junctions support two omitted "
        "segments, and the corrected model matches independently read orthologs "
        "whereas the annotated model matches none. The finding was judged **high "
        "certainty**[^1].\n\nThe evidence review is complete, and the independent "
        "reviews agreed on every sampled finding[^2]. This makes the result strong "
        "enough to prioritize a model revision, while the exact exon boundaries "
        "should still be checked before updating the annotation.\n\n"
        "[^1]: certainty: high\n"
        "[^2]: text: Two independent reviews agreed on 2 of 2 sampled findings "
        "(100%)"
    )


def test_an_investigator_reply_writes_no_raw_verdict_or_flag() -> None:
    facts = _facts(
        [
            _fact("stat_6694be4b", "gene_check", IntronAudit, _shifted([0], 1226)),
            _fact("stat_8dbbce57", "gene_check", IntronAudit, _shifted([827, 0], 723)),
        ],
        ["Afu2g18040", "NCU00776"],
        _FUNGI,
    )
    prose = (
        "The model audit is complete. Both gene models are judged "
        "incorrect as deposited, with high-confidence evidence of a "
        "shifted splice site rather than support for the annotated intron"
        " structure.\n\n- **Afu2g18040:** the first annotated intron has no"
        " supporting junction reads, while an alternative junction "
        "supports a shifted boundary. The other annotated intron is "
        "supported. The audit therefore recommends replacing the first "
        "junction with the supported alternative; the corrected coding "
        "frame is retained. See the audit evidence for the unsupported "
        "junction and its replacement: [stat:stat_6694be4b.verdict], "
        "[stat:stat_6694be4b.introns.0.reads], "
        "[stat:stat_6694be4b.unread.0.replacement.0.reads], "
        "[stat:stat_6694be4b.frameKept].\n\n- **NCU00776:** the second "
        "annotated intron has no supporting junction reads, while an "
        "alternative junction supports a downstream boundary shift. The "
        "other annotated intron is supported. The audit therefore "
        "recommends using the alternative boundary; the corrected coding "
        "frame is retained. See [stat:stat_8dbbce57.verdict], "
        "[stat:stat_8dbbce57.introns.1.reads], "
        "[stat:stat_8dbbce57.unread.0.replacement.0.reads], "
        "[stat:stat_8dbbce57.frameKept].\n\nThese are RNA-seq junction-"
        "supported model corrections, not evidence that either gene is "
        "absent or that the entire model should be discarded. The gene "
        "records are available here: [record:Afu2g18040] and "
        "[record:NCU00776]."
    )

    assert prose_faults(prose, facts) == []
    assert render_reply(prose, facts) == (
        "The model audit is complete. Both gene models are judged incorrect as "
        "deposited, with high-confidence evidence of a shifted splice site rather "
        "than support for the annotated intron structure.\n\n- **Afu2g18040:** the "
        "first annotated intron has no supporting junction reads, while an "
        "alternative junction supports a shifted boundary. The other annotated "
        "intron is supported. The audit therefore recommends replacing the first "
        "junction with the supported alternative; the corrected coding frame is "
        "retained. See the audit evidence for the unsupported junction and its "
        "replacement: [^1], 0, 1226, [^2].\n\n- **NCU00776:** the second annotated "
        "intron has no supporting junction reads, while an alternative junction "
        "supports a downstream boundary shift. The other annotated intron is "
        "supported. The audit therefore recommends using the alternative "
        "boundary; the corrected coding frame is retained. See[^3], 0, 723, "
        "[^4].\n\nThese are RNA-seq junction-supported model corrections, not "
        "evidence that either gene is absent or that the entire model should be "
        "discarded. The gene records are available here: "
        f"[Afu2g18040]({_FUNGI}Afu2g18040) and [NCU00776]({_FUNGI}NCU00776).\n\n"
        "[^1]: verdict: unsupported shifted\n"
        "[^2]: frame kept: yes\n"
        "[^3]: verdict: unsupported shifted\n"
        "[^4]: frame kept: yes"
    )


def test_a_review_reply_quotes_its_cause_once() -> None:
    result: JsonValue = {
        "unread": [{"replacement": [{"reads": 1226}]}],
        "frameKept": True,
    }
    facts = _facts(
        [
            _fact(
                "stat_a4effc19",
                "audit_finding",
                FindingDetail,
                {
                    "evidence": [
                        {
                            "payload": {
                                "kind": "confirmation",
                                "confirmation": {
                                    "check": "intron_support",
                                    "result": result,
                                },
                            }
                        }
                    ],
                    "review": {
                        "verdict": {
                            "verdict": "error",
                            "certainty": "medium",
                            "cause": _CAUSE,
                        },
                        "alreadyKnown": "not_searched",
                    },
                },
            )
        ],
        ["Afu2g18040"],
        _FUNGI,
    )
    prose = (
        "For [record:Afu2g18040], the audit found a localized shifted-"
        f"splice-site error in the deposited model{_DASH}not a missing or "
        "truncated gene. The annotated intron has no supporting RNA-seq "
        "junction reads, while a nearby replacement junction is supported"
        " by [stat:stat_a4effc19.evidence.0.payload.confirmation.result.u"
        "nread.0.replacement.0.reads] reads. The proposed correction "
        "preserves the coding frame [stat:stat_a4effc19.evidence.0.payloa"
        "d.confirmation.result.frameKept].\n\nThe finding was independently"
        " reviewed and retained as an error "
        "[stat:stat_a4effc19.review.verdict.verdict], with "
        "[stat:stat_a4effc19.review.verdict.certainty] certainty "
        "[stat:stat_a4effc19.review.verdict.cause]. Confidence is "
        "therefore meaningful but not definitive: no splice motif was "
        "recorded, and neither the annotated nor corrected model matched "
        "the surveyed orthologs "
        "[stat:stat_a4effc19.review.verdict.cause]. The review also did "
        "not search the literature "
        "[stat:stat_a4effc19.review.alreadyKnown]."
    )

    assert prose_faults(prose, facts) == []
    assert render_reply(prose, facts) == (
        f"For [Afu2g18040]({_FUNGI}Afu2g18040), the audit found a localized "
        f"shifted-splice-site error in the deposited model{_DASH}not a missing or "
        "truncated gene. The annotated intron has no supporting RNA-seq junction "
        "reads, while a nearby replacement junction is supported by 1226 reads. "
        "The proposed correction preserves the coding frame[^1].\n\nThe finding "
        "was independently reviewed and retained as an error[^2], with medium "
        "certainty[^3]. Confidence is therefore meaningful but not definitive: no "
        "splice motif was recorded, and neither the annotated nor corrected model "
        "matched the surveyed orthologs[^3]. The review also did not search the "
        "literature[^4].\n\n"
        "[^1]: frame kept: yes\n"
        "[^2]: verdict: error\n"
        f"[^3]: cause: {_CAUSE}\n"
        "[^4]: already known: not searched"
    )
