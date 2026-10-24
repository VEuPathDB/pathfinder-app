from __future__ import annotations

from typing import get_args

import pytest
from veupathdb_mcp.audit import (
    FusionVerdict,
    IntronVerdict,
    LengthClass,
    LengthVerdict,
    MissingVerdict,
    OrganelleVerdict,
    PseudogeneVerdict,
    SecVerdict,
    SideVerdict,
)

from pathfinder.domain.audit.confirmations import FindingVerdict
from pathfinder.domain.audit.findings import ErrorType, FindingStatus, UnresolvedStatus
from pathfinder.domain.audit.rates import Unresolved
from pathfinder.domain.audit.scope import CheckName
from pathfinder.domain.audit.stages import HaltKind
from pathfinder.domain.audit.verdicts import (
    LiteratureStatus,
    ReviewAgreement,
    ReviewStatus,
    VerdictKind,
)
from pathfinder.domain.audit.words import (
    CHECK_TITLES,
    ERROR_TYPE_DESCRIPTIONS,
    ERROR_TYPE_TITLES,
    HALT_SENTENCES,
    LITERATURE_SENTENCES,
    REVIEW_STATUS_SENTENCES,
    UNCHECKED_SENTENCES,
    UNRESOLVED_WORDS,
    VERDICT_KIND_SENTENCES,
    agreement_sentence,
    paper_sentence,
    verdict_sentence,
)

_VERDICTS: list[tuple[CheckName, tuple[FindingVerdict, ...]]] = [
    ("pseudogene_call", get_args(PseudogeneVerdict.__value__)),
    ("selenoprotein_end", get_args(SecVerdict.__value__)),
    ("gene_length", get_args(LengthVerdict.__value__)),
    ("gene_split", get_args(LengthVerdict.__value__)),
    (
        "gene_fusion",
        (*get_args(LengthClass.__value__), *get_args(FusionVerdict.__value__)),
    ),
    ("strain_model", get_args(SideVerdict.__value__)),
    ("missing_gene", get_args(MissingVerdict.__value__)),
    ("organelle_join", get_args(OrganelleVerdict.__value__)),
    ("intron_support", get_args(IntronVerdict.__value__)),
]


@pytest.mark.parametrize(("check", "verdicts"), _VERDICTS)
def test_every_verdict_a_check_gives_has_a_plain_sentence(
    check: CheckName, verdicts: tuple[FindingVerdict, ...]
) -> None:
    sentences = [verdict_sentence(check, verdict) for verdict in verdicts]
    assert [s for s in sentences if s == "" or "_" in s] == []


def test_every_check_has_a_title_and_its_verdicts_listed() -> None:
    assert sorted(check for check, _ in _VERDICTS) == sorted(get_args(CheckName))
    assert sorted(CHECK_TITLES) == sorted(get_args(CheckName))


def test_a_verdict_reads_only_under_the_check_that_gives_it() -> None:
    assert verdict_sentence("strain_model", "STRAIN_SHORT") == (
        "Related genomes match the reference, so the strain model is too short"
    )
    with pytest.raises(KeyError):
        verdict_sentence("organelle_join", "STRAIN_SHORT")
    assert (
        UNCHECKED_SENTENCES["unread"]
        == "Not checked: not read before the run's deadline"
    )


def test_every_name_a_report_states_has_its_words() -> None:
    assert sorted(ERROR_TYPE_TITLES) == sorted(get_args(ErrorType))
    assert sorted(ERROR_TYPE_DESCRIPTIONS) == sorted(get_args(ErrorType))
    assert sorted(VERDICT_KIND_SENTENCES) == sorted(get_args(VerdictKind))
    assert sorted(LITERATURE_SENTENCES) == sorted(get_args(LiteratureStatus))
    assert sorted(REVIEW_STATUS_SENTENCES) == sorted(get_args(ReviewStatus))
    assert sorted(UNCHECKED_SENTENCES) == sorted(get_args(FindingStatus))
    assert sorted(HALT_SENTENCES) == sorted(get_args(HaltKind))
    assert list(UNRESOLVED_WORDS) == list(get_args(UnresolvedStatus))


def test_the_unresolved_statuses_are_the_counts_an_unresolved_tally_holds() -> None:
    assert list(get_args(UnresolvedStatus)) == list(Unresolved.model_fields)


def test_a_paper_that_depends_on_the_model_reads_in_words() -> None:
    assert [paper_sentence(depends=depends) for depends in (True, False, None)] == [
        "A published study depends on this gene's model",
        "No published study was found that depends on this gene's model",
        "Not checked whether a published study depends on this gene's model",
    ]


def test_the_reviews_agreement_reads_with_its_share() -> None:
    assert agreement_sentence(ReviewAgreement(sampled=3, agreed=2)) == (
        "Two independent reviews agreed on 2 of 3 sampled findings (67%)"
    )
    assert agreement_sentence(ReviewAgreement(sampled=0, agreed=0)) == (
        "No finding was reviewed twice, so the reviews' agreement is not measured"
    )


def test_a_split_pair_left_unchecked_names_the_split_not_a_short_model() -> None:
    assert (
        verdict_sentence("gene_split", "NOT_CHECKED"),
        verdict_sentence("gene_length", "NOT_CHECKED"),
    ) == (
        (
            "The site's ortholog group does not call the pair a split, so their DNA "
            "was not read"
        ),
        (
            "The site's whole ortholog group does not class the model as short, so "
            "its DNA was not read"
        ),
    )
