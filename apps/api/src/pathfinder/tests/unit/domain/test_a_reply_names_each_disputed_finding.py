from __future__ import annotations

from pathfinder.ai.lead._lead_audit_instructions import AUDIT_RULES
from pathfinder.ai.lead.contract_messages import unrendered_prose_message
from pathfinder.domain.reply_references import ProseFault, prose_faults
from pathfinder.domain.statistic_facts import StatisticFact
from pathfinder.domain.statistic_rows import model_rows
from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.services.audit.review_views import AgreementView, FindingLine

_RUN = "stat_a1e56ea3"
_DISPUTE = (
    "The two independent reviews disagree: the first finds no error, the second "
    "keeps the error"
)
_RECORDED = (
    "The independent review agreed across the sampled findings "
    f"[cite:{_RUN}.agreement.text], and all retained error classes are marked "
    "high confidence."
)


def _facts() -> TurnFacts:
    agreement = AgreementView(
        sampled=9,
        agreed=8,
        share=0.889,
        text="Two independent reviews agreed on 8 of 9 sampled findings (89%)",
    )
    disputed = FindingLine(
        id=28,
        genes=["PfNF54_130012200:pseudogene", "PF3D7_1307000"],
        genome="Plasmodium falciparum NF54",
        error_type=None,
        error_title=None,
        certainty=None,
        impact=0.25,
        reviewed_impact=None,
        reviews_disagree=True,
        disagreement_text=_DISPUTE,
    )
    rows = [*model_rows(agreement, "agreement"), *model_rows(disputed, "disputed.0")]
    run = StatisticFact(id=_RUN, kind="audit_run", title="Audit run", rows=rows)
    return TurnFacts(audit_statistics=[run])


def test_a_reply_that_reads_a_disputed_run_and_names_no_dispute_is_refused() -> None:
    assert prose_faults(_RECORDED, _facts()) == [
        ProseFault(
            token=f"[stat:{_RUN}.disputed.0.id]",
            kind="unnamed_dispute",
            references=(f"[cite:{_RUN}.disputed.0.disagreementText]",),
        )
    ]


def test_a_reply_that_names_the_dispute_holds() -> None:
    prose = (
        f"Two independent reviews agreed on [stat:{_RUN}.agreement.agreed] of "
        f"[stat:{_RUN}.agreement.sampled] sampled findings. They split on finding "
        f"[stat:{_RUN}.disputed.0.id] [cite:{_RUN}.disputed.0.disagreementText]."
    )

    assert prose_faults(prose, _facts()) == []


def test_a_reply_that_reads_nothing_of_the_run_names_no_dispute() -> None:
    assert prose_faults("The audit is done.", _facts()) == []


def test_the_refusal_tells_the_reply_to_name_the_dispute() -> None:
    (fault,) = prose_faults(_RECORDED, _facts())

    assert unrendered_prose_message([fault]).splitlines()[-1] == (
        f"- ``[stat:{_RUN}.disputed.0.id]``: the two reviews of this finding "
        "disagree, and a reply that reads this run names each disputed finding: "
        "name its genes by their record references and write "
        f"``[cite:{_RUN}.disputed.0.disagreementText]`` after your words for the "
        "disagreement."
    )


def test_a_group_reference_offers_only_the_values_that_stand_in_place() -> None:
    prose = f"The reviews agreed on [stat:{_RUN}.agreement]."

    assert [(f.kind, f.references) for f in prose_faults(prose, _facts())] == [
        (
            "unheld_reference",
            (
                f"[stat:{_RUN}.agreement.sampled]",
                f"[stat:{_RUN}.agreement.agreed]",
                f"[stat:{_RUN}.agreement.share]",
            ),
        ),
        ("unnamed_dispute", (f"[cite:{_RUN}.disputed.0.disagreementText]",)),
    ]


def test_the_lead_is_told_to_name_a_dispute_and_place_the_agreement() -> None:
    told = [
        line for line in AUDIT_RULES.splitlines() if line.startswith("- **A dispute")
    ]

    assert told == [
        (
            "- **A dispute between the two reviews is named.** A run whose two "
            "reviews disagree on a finding lists it under ``disputed``, and a "
            "reply that reads the run names each one: its genes and "
            "``[cite:<fact id>.disputed.<n>.disagreementText]``. The agreement is "
            "a number the reply places: ``[stat:<fact id>.agreement.agreed]`` of "
            "``[stat:<fact id>.agreement.sampled]``."
        )
    ]
