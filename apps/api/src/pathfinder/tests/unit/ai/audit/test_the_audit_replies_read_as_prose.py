"""The Lead's audit replies of a recorded run, each value placed by ``stat`` and each citation by ``cite``, render as single prose."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, JsonValue
from veupathdb_mcp.audit import IntronAudit

from pathfinder.domain.record_facts import SourceFact
from pathfinder.domain.reply_references import prose_faults, shown_reply
from pathfinder.domain.statistic_facts import StatisticFact, StatisticKind
from pathfinder.domain.statistic_rows import schema_rows
from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.services.audit.finding_views import FindingDetail
from pathfinder.services.audit.views import AuditRunView

_PLASMO = "https://qa.plasmodb.org/plasmo.qa/app/record/gene/"
_VECTOR = "https://qa.vectorbase.org/vectorbase.qa/app/record/gene/"
_FUNGI = "https://qa.fungidb.org/fungidb.qa/app/record/gene/"
_DASH = chr(0x2014)
_RSQUO = chr(0x2019)
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


_RUN_V = _fact(
    "stat_c436453c",
    "audit_run",
    AuditRunView,
    {
        "errorTypes": [
            {
                "certainty": "high",
                "description": "RNA-seq reads join an exon the model does not have.",
            }
        ],
        "agreement": {
            "text": "Two independent reviews agreed on 2 of 2 sampled findings (100%)"
        },
    },
)
_REVIEWED: JsonValue = {
    "unread": [{"replacement": [{"reads": 1226}]}],
    "frameKept": True,
}
_FACTS: dict[str, TurnFacts] = {
    "P/t2": _facts(
        [
            _fact(
                "stat_ad5c5b01",
                "audit_finding",
                FindingDetail,
                {
                    "finding": {
                        "id": 1,
                        "certainty": "high",
                        "verdictText": (
                            "RNA-seq reads join an exon the model does not have"
                        ),
                    },
                    "review": {"verdict": {"verdict": "undecided"}},
                    "reviewText": {"literatureText": "The literature was not searched"},
                },
            )
        ],
        ["PcyM_0736700"],
        _PLASMO,
    ),
    "V/t2": _facts([_RUN_V], ["AFAF012298"], _VECTOR),
    "V/t1": _facts([_RUN_V], ["AFAF012298", "AATE004286"], _VECTOR),
    "F/t1": _facts(
        [
            _fact("stat_6694be4b", "gene_check", IntronAudit, _shifted([0], 1226)),
            _fact("stat_8dbbce57", "gene_check", IntronAudit, _shifted([827, 0], 723)),
        ],
        ["Afu2g18040", "NCU00776"],
        _FUNGI,
    ),
    "F/t2": _facts(
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
                                    "result": _REVIEWED,
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
    ),
    "S/t2": _facts(
        [
            _fact(
                "stat_fa67648b",
                "audit_run",
                AuditRunView,
                {
                    "errorTypes": [
                        {"count": 7, "certainty": "high"},
                        {"count": 1, "certainty": "high"},
                        {"count": 1, "certainty": "medium"},
                    ],
                    "agreement": {"agreed": 8, "sampled": 9, "share": 0.889},
                },
            )
        ],
        [],
        _PLASMO,
    ),
}


_P_T2_PROSE = (
    "For [record:PcyM_0736700], the audit found a confirmed missing-"
    "exon problem in the annotated transcript: RNA-seq junctions "
    "support an exon structure that the current model lacks, so the "
    "model is judged unsupported as annotated "
    "[cite:stat_ad5c5b01.finding.verdictText].\n\nConfidence in the "
    "underlying RNA-seq finding is high "
    "[cite:stat_ad5c5b01.finding.certainty]. However, the separate "
    "adjudication review was undecided "
    "[cite:stat_ad5c5b01.review.verdict.verdict]: it stopped before "
    "writing a valid review, and no literature check was performed "
    "[cite:stat_ad5c5b01.reviewText.literatureText]. So this is strong "
    "evidence that the current model is missing an exon, but not a "
    "completed expert adjudication of the proposed correction."
)
_P_T2_SHOWN = (
    "For [PcyM_0736700](https://qa.plasmodb.org/plasmo.qa/app/record/ge"
    "ne/PcyM_0736700), the audit found a confirmed missing-exon problem"
    " in the annotated transcript: RNA-seq junctions support an exon "
    "structure that the current model lacks, so the model is judged "
    "unsupported as annotated[^1].\n\nConfidence in the underlying RNA-"
    "seq finding is high[^2]. However, the separate adjudication review"
    " was undecided[^3]: it stopped before writing a valid review, and "
    "no literature check was performed[^4]. So this is strong evidence "
    "that the current model is missing an exon, but not a completed "
    "expert adjudication of the proposed correction.\n\n[^1]: finding "
    "verdict text: RNA-seq reads join an exon the model does not have\n"
    "[^2]: finding certainty: high\n[^3]: review verdict: undecided\n"
    "[^4]: review text literature text: The literature was not searched"
)
_V_T2_PROSE = (
    "For [record:AFAF012298], the audit found a **missing internal "
    "exon**: RNA-seq replacement junctions support two omitted "
    "segments, and the corrected model matches independently read "
    "orthologs whereas the annotated model matches none. The finding "
    "was judged **high certainty** "
    "[cite:stat_c436453c.errorTypes.0.certainty].\n\nThe evidence review "
    "is complete, and the independent reviews agreed on every sampled "
    "finding [cite:stat_c436453c.agreement.text]. This makes the result"
    " strong enough to prioritize a model revision, while the exact "
    "exon boundaries should still be checked before updating the "
    "annotation."
)
_V_T2_SHOWN = (
    "For [AFAF012298](https://qa.vectorbase.org/vectorbase.qa/app/recor"
    "d/gene/AFAF012298), the audit found a **missing internal exon**: "
    "RNA-seq replacement junctions support two omitted segments, and "
    "the corrected model matches independently read orthologs whereas "
    "the annotated model matches none. The finding was judged **high "
    "certainty**[^1].\n\nThe evidence review is complete, and the "
    "independent reviews agreed on every sampled finding[^2]. This "
    "makes the result strong enough to prioritize a model revision, "
    "while the exact exon boundaries should still be checked before "
    "updating the annotation.\n\n[^1]: error types certainty: high\n[^2]: "
    "agreement text: Two independent reviews agreed on 2 of 2 sampled "
    "findings (100%)"
)
_V_T1_PROSE = (
    "The VectorBase audit is complete for both requested models. RNA-"
    "seq junction evidence supports the same high-certainty issue in "
    "each: an exon is missing from the annotated model, meaning reads "
    "join an exon that the model does not include "
    "[cite:stat_c436453c.errorTypes.0.description]. The affected models"
    " are [record:AFAF012298] and [record:AATE004286]. The audit's "
    "evidence review is still queued, so these are confirmed screening "
    f"findings but do not yet include the reviewer{_RSQUO}s final "
    "interpretation. I recommend revising each model to evaluate the "
    "missing exon and then rechecking the junction support."
)
_V_T1_SHOWN = (
    "The VectorBase audit is complete for both requested models. RNA-"
    "seq junction evidence supports the same high-certainty issue in "
    "each: an exon is missing from the annotated model, meaning reads "
    "join an exon that the model does not include[^1]. The affected "
    "models are [AFAF012298](https://qa.vectorbase.org/vectorbase.qa/ap"
    "p/record/gene/AFAF012298) and [AATE004286](https://qa.vectorbase.o"
    "rg/vectorbase.qa/app/record/gene/AATE004286). The audit's evidence"
    " review is still queued, so these are confirmed screening findings"
    f" but do not yet include the reviewer{_RSQUO}s final interpretation. I "
    "recommend revising each model to evaluate the missing exon and "
    "then rechecking the junction support.\n\n[^1]: error types "
    "description: RNA-seq reads join an exon the model does not have."
)
_F_T1_PROSE = (
    "The model audit is complete. Both gene models are judged incorrect"
    " as deposited, with high-confidence evidence of a shifted splice "
    "site rather than support for the annotated intron structure.\n\n- "
    "**Afu2g18040:** the first annotated intron has no supporting "
    "junction reads, while an alternative junction supports a shifted "
    "boundary. The other annotated intron is supported. The audit "
    "therefore recommends replacing the first junction with the "
    "supported alternative; the corrected coding frame is retained. See"
    " the audit evidence for the unsupported junction and its "
    "replacement: [stat:stat_6694be4b.verdict], "
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
_F_T1_SHOWN = (
    "The model audit is complete. Both gene models are judged incorrect"
    " as deposited, with high-confidence evidence of a shifted splice "
    "site rather than support for the annotated intron structure.\n\n- "
    "**Afu2g18040:** the first annotated intron has no supporting "
    "junction reads, while an alternative junction supports a shifted "
    "boundary. The other annotated intron is supported. The audit "
    "therefore recommends replacing the first junction with the "
    "supported alternative; the corrected coding frame is retained. See"
    " the audit evidence for the unsupported junction and its "
    "replacement: unsupported shifted, 0, 1226, Yes.\n\n- **NCU00776:** "
    "the second annotated intron has no supporting junction reads, "
    "while an alternative junction supports a downstream boundary "
    "shift. The other annotated intron is supported. The audit "
    "therefore recommends using the alternative boundary; the corrected"
    " coding frame is retained. See unsupported shifted, 0, 723, Yes.\n\n"
    "These are RNA-seq junction-supported model corrections, not "
    "evidence that either gene is absent or that the entire model "
    "should be discarded. The gene records are available here: [Afu2g18"
    "040](https://qa.fungidb.org/fungidb.qa/app/record/gene/Afu2g18040)"
    " and [NCU00776](https://qa.fungidb.org/fungidb.qa/app/record/gene/"
    "NCU00776)."
)
_F_T2_PROSE = (
    "For [record:Afu2g18040], the audit found a localized shifted-"
    f"splice-site error in the deposited model{_DASH}not a missing or "
    "truncated gene. The annotated intron has no supporting RNA-seq "
    "junction reads, while a nearby replacement junction is supported "
    "by [stat:stat_a4effc19.evidence.0.payload.confirmation.result.unre"
    "ad.0.replacement.0.reads] reads. The proposed correction preserves"
    " the coding frame [cite:stat_a4effc19.evidence.0.payload.confirmat"
    "ion.result.frameKept].\n\nThe finding was independently reviewed and"
    " retained as an error [cite:stat_a4effc19.review.verdict.verdict],"
    " with [stat:stat_a4effc19.review.verdict.certainty] certainty "
    "[cite:stat_a4effc19.review.verdict.cause]. Confidence is therefore"
    " meaningful but not definitive: no splice motif was recorded, and "
    "neither the annotated nor corrected model matched the surveyed "
    "orthologs [cite:stat_a4effc19.review.verdict.cause]. The review "
    "also did not search the literature "
    "[cite:stat_a4effc19.review.alreadyKnown]."
)
_F_T2_SHOWN = (
    "For [Afu2g18040](https://qa.fungidb.org/fungidb.qa/app/record/gene"
    "/Afu2g18040), the audit found a localized shifted-splice-site "
    f"error in the deposited model{_DASH}not a missing or truncated gene. The "
    "annotated intron has no supporting RNA-seq junction reads, while a"
    " nearby replacement junction is supported by 1226 reads. The "
    "proposed correction preserves the coding frame[^1].\n\nThe finding "
    "was independently reviewed and retained as an error[^2], with "
    "medium certainty[^3]. Confidence is therefore meaningful but not "
    "definitive: no splice motif was recorded, and neither the "
    "annotated nor corrected model matched the surveyed orthologs[^3]. "
    "The review also did not search the literature[^4].\n\n[^1]: result "
    "frame kept: Yes\n[^2]: review verdict: error\n[^3]: verdict cause: "
    "The annotated intron is unsupported by RNA-seq, whereas a nearby "
    "replacement junction is supported by 1,226 reads and preserves the"
    " coding frame. This supports a shifted splice site, but certainty "
    "remains medium because no splice motif was recorded and neither "
    "the annotated nor corrected model matched the surveyed orthologs.\n"
    "[^4]: review already known: not searched"
)
_S_T2_PROSE = (
    "The NF54 audit found three main error patterns.\n\n- **Intact genes "
    "called pseudogenes:** this was the largest class. Direct sequence "
    "confirmation reconstructed complete reference coding sequences, "
    "with no premature stops or amino-acid differences. That makes "
    "these findings **high confidence**: "
    "[stat:stat_fa67648b.errorTypes.0.count] findings, with "
    "[stat:stat_fa67648b.errorTypes.0.certainty] certainty.\n\n- **A "
    "truncated gene model:** the model was substantially shorter than "
    "its reference and related proteins, while the surrounding NF54 "
    "sequence encoded the missing region. There was no unknown sequence"
    " or contig-edge explanation, supporting a genuine truncation with "
    "**high confidence**: [stat:stat_fa67648b.errorTypes.1.count] "
    "finding, with [stat:stat_fa67648b.errorTypes.1.certainty] "
    "certainty.\n\n- **A split gene model:** neighboring models contained"
    " complementary parts of a single cytochrome b protein on the same "
    "strand and contig. Sequence, relative-genome, and protein evidence"
    " support the split-model interpretation, but with **medium "
    "confidence**: [stat:stat_fa67648b.errorTypes.2.count] finding, "
    "with [stat:stat_fa67648b.errorTypes.2.certainty] certainty.\n\n"
    "Across the reviewed sample, independent reviews agreed on "
    "[stat:stat_fa67648b.agreement.agreed] of "
    "[stat:stat_fa67648b.agreement.sampled] findings, corresponding to "
    "[stat:stat_fa67648b.agreement.share] agreement. In practical "
    "terms, the strongest conclusions are the intact-gene pseudogene "
    "calls and the truncation; the split cytochrome b model is well "
    "supported but deserves more manual review.\n\nThe audit itself did "
    "address split genes and gene-length problems. The earlier search "
    "strategy did not: its remaining gaps are specifically **split "
    "genes** and **gene length problems**, because the site exposed no "
    "corresponding searches for those criteria. Nothing in the strategy"
    " changed while I summarized the audit."
)
_S_T2_SHOWN = (
    "The NF54 audit found three main error patterns.\n\n- **Intact genes "
    "called pseudogenes:** this was the largest class. Direct sequence "
    "confirmation reconstructed complete reference coding sequences, "
    "with no premature stops or amino-acid differences. That makes "
    "these findings **high confidence**: 7 findings, with high "
    "certainty.\n\n- **A truncated gene model:** the model was "
    "substantially shorter than its reference and related proteins, "
    "while the surrounding NF54 sequence encoded the missing region. "
    "There was no unknown sequence or contig-edge explanation, "
    "supporting a genuine truncation with **high confidence**: 1 "
    "finding, with high certainty.\n\n- **A split gene model:** "
    "neighboring models contained complementary parts of a single "
    "cytochrome b protein on the same strand and contig. Sequence, "
    "relative-genome, and protein evidence support the split-model "
    "interpretation, but with **medium confidence**: 1 finding, with "
    "medium certainty.\n\nAcross the reviewed sample, independent reviews"
    " agreed on 8 of 9 findings, corresponding to 88.9% agreement. In "
    "practical terms, the strongest conclusions are the intact-gene "
    "pseudogene calls and the truncation; the split cytochrome b model "
    "is well supported but deserves more manual review.\n\nThe audit "
    "itself did address split genes and gene-length problems. The "
    "earlier search strategy did not: its remaining gaps are "
    "specifically **split genes** and **gene length problems**, because"
    " the site exposed no corresponding searches for those criteria. "
    "Nothing in the strategy changed while I summarized the audit."
)


_REPLIES = {
    "P/t2": (_P_T2_PROSE, _P_T2_SHOWN),
    "V/t2": (_V_T2_PROSE, _V_T2_SHOWN),
    "V/t1": (_V_T1_PROSE, _V_T1_SHOWN),
    "F/t1": (_F_T1_PROSE, _F_T1_SHOWN),
    "F/t2": (_F_T2_PROSE, _F_T2_SHOWN),
    "S/t2": (_S_T2_PROSE, _S_T2_SHOWN),
}


@pytest.mark.parametrize("run", list(_REPLIES))
def test_a_recorded_reply_renders_as_single_prose(run: str) -> None:
    prose, shown = _REPLIES[run]

    assert prose_faults(prose, _FACTS[run]) == []
    assert shown_reply(prose, _FACTS[run], "") == shown
