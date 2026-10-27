"""The verification section the Lead reads in full carries the check's review:
each check on the site, each column, each sampled gene and each source."""

from __future__ import annotations

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.ledger_render import render_verification_full
from pathfinder.ai.lead.ledger_sections import VerificationSection
from pathfinder.domain.caveats import ControlsCaveat, SampleCaveat
from pathfinder.domain.citations import (
    Citation,
)
from pathfinder.domain.evidence import (
    NamedControlSet,
    SampledGene,
    VerificationReview,
    WithheldEvidence,
)
from pathfinder.domain.site_checks import SiteCheck
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.tests._support.column_fits import tm_fit


def test_the_full_section_lists_the_review() -> None:
    review = VerificationReview(
        checks=[
            SiteCheck(
                kind="result_count",
                subject="the strategy on the site",
                status="pass",
                evidence="the result step 11 ('Signal') holds 840 records",
            ),
            SiteCheck(
                kind=ConstraintKind.OTHER,
                subject="at least 2 transmembrane domains",
                status="unchecked",
                evidence="no check reads this requirement on the site",
            ),
        ],
        column_fits=[tm_fit(840, 840)],
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

    assert rendered.split("\n### Checks on the site\n")[1].split("\n\n")[0] == (
        "- [pass] the strategy on the site: the result step 11 ('Signal') holds "
        "840 records\n"
        "- [unchecked] at least 2 transmembrane domains: no check reads this "
        "requirement on the site"
    )
    assert rendered.split("\n### Columns\n")[1].split("\n\n")[0] == (
        "- [all] c_tm: 840 of 840 transcripts fit # TM Domains (2 to 99)"
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
            SampleCaveat(fit=tm_fit(12, 40)),
        ],
    )

    rendered = render_verification_full(
        VerificationSection(digest=digest, caveats=list(digest.caveats))
    )

    assert rendered.split("\n### Caveats\n")[1].split("\n\n")[0] == (
        "- 3 of 5 positive controls returned (control set Kinases, id set-a)\n"
        "- 3 of 5 positive controls returned (control set Exported, id set-b)\n"
        "- 1 of 2 positive controls returned\n"
        "- 12 of 40 transcripts fit # TM Domains (2 to 99)"
    )


def test_the_full_section_lists_what_the_check_withheld() -> None:
    withheld = WithheldEvidence(
        kind="sampled_gene",
        sentence=(
            "The review lists sampled gene `PF3D7_0102200`, and no read_gene_record "
            "call of this turn read its record."
        ),
    )
    digest = VerificationDigest(
        disposition=PhaseDisposition.DONE,
        prose="Checked.",
        reason="r",
        success=True,
        review=VerificationReview(withheld=[withheld]),
    )

    rendered = render_verification_full(VerificationSection(digest=digest))

    assert rendered.split("\n### Withheld from the evidence card\n")[1] == (
        f"- {withheld.sentence}"
    )
