"""The verification section the Lead reads in full carries the check's review:
each requirement row, each sampled gene and each source."""

from __future__ import annotations

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.ledger_render import render_verification_full
from pathfinder.ai.lead.ledger_sections import VerificationSection
from pathfinder.domain.caveats import ControlsCaveat, SampleCaveat
from pathfinder.domain.evidence import (
    Citation,
    NamedControlSet,
    RequirementCheck,
    SampledGene,
    VerificationReview,
)


def test_the_full_section_lists_the_review() -> None:
    review = VerificationReview(
        requirements=[
            RequirementCheck(
                text="with a signal peptide",
                turn=1,
                answered_by=["s1"],
                how="search",
                status="met",
                note="GenesWithSignalPeptide",
            ),
            RequirementCheck(
                text="at least 2 transmembrane domains",
                turn=2,
                how="search",
                status="unmet",
                note="no step reads transmembrane domains",
            ),
        ],
        sampled_genes=[
            SampledGene(
                gene_id="PF3D7_0100200",
                product="histone H3",
                organism="Plasmodium falciparum 3D7",
                fits="no",
                why="a histone carries no signal peptide",
            )
        ],
        sources=[
            Citation(
                kind="literature",
                label="Exportome",
                doi="10.1038/nature12970",
                why="lists exported proteins",
            )
        ],
    )
    digest = VerificationDigest(
        disposition=PhaseDisposition.DONE,
        prose="Checked.",
        reason="one requirement unmet",
        success=False,
        review=review,
    )

    rendered = render_verification_full(VerificationSection(digest=digest))

    assert rendered.split("\n### Requirements\n")[1].split("\n\n")[0] == (
        "- [met] with a signal peptide (message 1, search; answered by s1): "
        "GenesWithSignalPeptide\n"
        "- [unmet] at least 2 transmembrane domains (message 2, search; answered "
        "by nothing): no step reads transmembrane domains"
    )
    assert rendered.split("\n### Sampled genes\n")[1].split("\n\n")[0] == (
        "- PF3D7_0100200, histone H3 (Plasmodium falciparum 3D7): fits no - a "
        "histone carries no signal peptide"
    )
    assert rendered.split("\n### Sources\n")[1] == (
        "- Exportome (10.1038/nature12970): lists exported proteins"
    )


def test_two_sets_on_one_step_are_two_caveat_lines_that_name_their_set() -> None:
    digest = VerificationDigest(
        disposition=PhaseDisposition.DONE,
        prose="Checked.",
        reason="controls missed",
        success=True,
        caveats=[
            ControlsCaveat(
                positives_returned=3,
                positives_total=5,
                control_set=NamedControlSet(id="set-a", name="Kinases"),
            ),
            ControlsCaveat(
                positives_returned=3,
                positives_total=5,
                control_set=NamedControlSet(id="set-b", name="Exported"),
            ),
            ControlsCaveat(positives_returned=1, positives_total=2),
            SampleCaveat(unclear=2, misfit=0, total=8),
        ],
    )

    rendered = render_verification_full(VerificationSection(digest=digest))

    assert rendered.split("\n### Caveats\n")[1].split("\n\n")[0] == (
        "- 3 of 5 positive controls returned (control set Kinases, id set-a)\n"
        "- 3 of 5 positive controls returned (control set Exported, id set-b)\n"
        "- 1 of 2 positive controls returned\n"
        "- 2 of 8 sampled genes unclear"
    )
