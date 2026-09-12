"""Correctness tests for gene-record classification — hand-computed
expected partitions from explicit set membership.

``classify_records`` tags each WDK record with a ``classification`` label
(TP/FP/FN/TN/None) based on whether its primary-key gene ID appears in the
corresponding curated set. ``_classify_gene_id`` is the pure decision core:
it resolves overlap by precedence (TP > FP > FN > TN) and strips the WDK
transcript version suffix (``GENE.1`` -> ``GENE``) only when the full ID
matches nothing.
"""

from __future__ import annotations

from veupathdb.domain import WDKRecordIdPart
from veupathdb.wdk import WDKRecordInstance

from pathfinder.services.experiment.classification import (
    _classify_gene_id,
    classify_records,
)


def _record(gene_id: str) -> WDKRecordInstance:
    return WDKRecordInstance(id=[WDKRecordIdPart(name="gene", value=gene_id)])


def test_disjoint_sets_partition() -> None:
    # Hand-computed: tp g1,g2 | fp g3 | fn g4 | tn g5; each gene resolves
    # to exactly the set it belongs to.
    assert _classify_gene_id("g1", {"g1", "g2"}, {"g3"}, {"g4"}, {"g5"}) == "TP"
    assert _classify_gene_id("g2", {"g1", "g2"}, {"g3"}, {"g4"}, {"g5"}) == "TP"
    assert _classify_gene_id("g3", {"g1", "g2"}, {"g3"}, {"g4"}, {"g5"}) == "FP"
    assert _classify_gene_id("g4", {"g1", "g2"}, {"g3"}, {"g4"}, {"g5"}) == "FN"
    assert _classify_gene_id("g5", {"g1", "g2"}, {"g3"}, {"g4"}, {"g5"}) == "TN"


def test_gene_in_no_set_is_unclassified() -> None:
    assert _classify_gene_id("g9", {"g1"}, {"g2"}, {"g3"}, {"g4"}) is None


def test_empty_sets_yield_none() -> None:
    assert _classify_gene_id("g1", set(), set(), set(), set()) is None


def test_none_gene_id_yields_none() -> None:
    assert _classify_gene_id(None, {"g1"}, set(), set(), set()) is None


def test_empty_string_gene_id_yields_none() -> None:
    assert _classify_gene_id("", {"g1"}, set(), set(), set()) is None


def test_overlap_precedence_tp_over_fp() -> None:
    assert _classify_gene_id("g1", {"g1"}, {"g1"}, {"g1"}, {"g1"}) == "TP"


def test_overlap_precedence_fp_over_fn() -> None:
    assert _classify_gene_id("g1", set(), {"g1"}, {"g1"}, {"g1"}) == "FP"


def test_overlap_precedence_fn_over_tn() -> None:
    assert _classify_gene_id("g1", set(), set(), {"g1"}, {"g1"}) == "FN"


def test_version_suffix_stripped_to_base_match() -> None:
    # full "GENE.1" matches nothing; base "GENE" is in tp_ids.
    assert _classify_gene_id("GENE.1", {"GENE"}, set(), set(), set()) == "TP"


def test_full_versioned_id_matches_before_base() -> None:
    # full "GENE.1" is itself stored in tp_ids; no stripping needed.
    assert _classify_gene_id("GENE.1", {"GENE.1"}, set(), set(), set()) == "TP"


def test_full_id_match_wins_over_base_id_in_other_set() -> None:
    # The loop tries every set for the full id before the base id, so a
    # full-id hit in a lower precedence set beats a base-id hit higher up.
    assert _classify_gene_id("GENE.1", {"GENE"}, set(), set(), {"GENE.1"}) == "TN"


def test_leading_dot_id_has_no_base_candidate() -> None:
    # rfind(".") == 0 is not > 0, so ".1" produces no base candidate.
    assert _classify_gene_id(".1", {"1"}, set(), set(), set()) is None


def test_multiple_dots_strips_only_last_segment() -> None:
    # rfind takes the last dot: "A.B.1" -> base "A.B".
    assert _classify_gene_id("A.B.1", {"A.B"}, set(), set(), set()) == "TP"
    assert _classify_gene_id("A.B.1", {"A"}, set(), set(), set()) is None


def test_classify_records_attaches_labels_and_passes_through_id() -> None:
    records = [_record("g1"), _record("g3"), _record("g4"), _record("g9")]
    out = classify_records(
        records,
        tp_ids={"g1"},
        fp_ids={"g3"},
        fn_ids={"g4"},
        tn_ids={"g5"},
    )
    assert [r["classification"] for r in out] == ["TP", "FP", "FN", None]
    assert out[0]["id"] == [{"name": "gene", "value": "g1"}]


def test_classify_records_strips_whitespace_in_pk() -> None:
    out = classify_records(
        [_record("  g1  ")],
        tp_ids={"g1"},
        fp_ids=set(),
        fn_ids=set(),
        tn_ids=set(),
    )
    assert out[0]["classification"] == "TP"


def test_classify_records_empty_input() -> None:
    assert classify_records([], {"g1"}, set(), set(), set()) == []


def test_classify_records_record_without_id_is_none() -> None:
    out = classify_records(
        [WDKRecordInstance()],
        tp_ids={"g1"},
        fp_ids=set(),
        fn_ids=set(),
        tn_ids=set(),
    )
    assert out[0]["classification"] is None
