from __future__ import annotations

from typing import Literal

from veupathdb_mcp.audit import (
    GeneFusionAudit,
    GeneLengthAudit,
    LengthCheck,
    LengthScreen,
    NoRelatives,
    NotRead,
    StrainModelAudit,
    WindowState,
)

from pathfinder.domain.audit.facts import (
    NONE,
    NOT_READ,
    TIER_WORDS,
    YES_NO,
    Fact,
    code_text,
    known,
    listed,
    residues,
    runs_text,
    unread_facts,
)
from pathfinder.domain.audit.words import LENGTH_SENTENCES

_PARTS: dict[WindowState | Literal["part1", "part2"], str] = {
    "model": "in the model",
    "genome_same_strand": "encoded on the same strand outside the model",
    "genome_other_strand": "encoded on the other strand",
    "absent": "not encoded",
    "weak": "matched weakly",
    "part1": "in the first model",
    "part2": "in the second model",
}
_NO_RELATIVES: dict[NoRelatives, str] = {
    "RESIDUAL_GROUP": "the ortholog group is a residual group",
    "PARALOGS": "the related genomes do not hold one copy each",
    "FEWER_THAN_TWO": "fewer than two independent related genomes hold the gene",
}
_NOT_READ: dict[NotRead, str] = {
    "NO_LOST_RUN": "The strain protein lacks no run of the reference protein",
    "UNQUALIFIED": "The ortholog group is a residual group",
    "PARALOG_IN_WINDOW": "A paralog lies in the region the check reads",
}


def _parts(check: LengthCheck) -> str:
    if check.windows == 0:
        return NOT_READ
    counted = [f"{n:,} {_PARTS[label]}" for label, n in check.counts.items()]
    return f"{check.windows:,}: {', '.join(counted)}"


def _dna(check: LengthCheck) -> tuple[Fact, ...]:
    ns = check.ns_in_window
    return (
        Fact(label="Parts of the reference protein", value=_parts(check)),
        Fact(
            label="Unknown bases in the region read",
            value=NOT_READ if ns is None else f"{ns:,}",
        ),
        Fact(label="At a contig end", value=YES_NO[check.at_contig_edge]),
    )


def _screen(screen: LengthScreen) -> tuple[Fact, ...]:
    ratio = screen.ratio
    one = len(screen.genes) == 1
    return (
        Fact(label="Model" if one else "Models", value=listed(screen.genes)),
        Fact(label="Reference gene", value=known(screen.reference_gene)),
        Fact(
            label="Ortholog group median",
            value=f"{screen.group_median:g} residues over {screen.organisms:,} organisms",
        ),
        Fact(
            label="Length against the median",
            value=NOT_READ if ratio is None else f"{ratio:g} times the median length",
        ),
    )


def length_facts(result: GeneLengthAudit) -> tuple[Fact, ...]:
    return (
        *_screen(result),
        *_dna(result),
        Fact(
            label="Genetic code",
            value=code_text(result.code, inferred=result.code_inferred),
        ),
        *unread_facts(result.evidence_unread),
    )


def fusion_facts(result: GeneFusionAudit) -> tuple[Fact, ...]:
    fusion = result.fusion
    merged = result.merged
    found = (
        ()
        if fusion is None
        else (
            Fact(label="Extra residues", value=runs_text(fusion.extra)),
            Fact(
                label="Extra parts that match a neighbour",
                value=f"{fusion.neighbour_windows:,} of {fusion.extra_windows:,}",
            ),
            Fact(
                label="Partner gene",
                value=NONE if fusion.partner is None else fusion.partner,
            ),
            Fact(label="Neighbours read", value=listed(fusion.neighbours)),
            Fact(label="Product", value=fusion.product),
            Fact(label="Partner's ortholog group", value=known(fusion.partner_group)),
            Fact(label="Partner's product", value=known(fusion.partner_product)),
            Fact(
                label="Partner's copies in the group",
                value=NOT_READ
                if fusion.partner_copies is None
                else listed(fusion.partner_copies),
            ),
        )
    )
    joined = (
        ()
        if merged is None
        else (
            Fact(
                label="Merged model",
                value=f"{merged.gene} on {merged.seqid}, bases {merged.start:,} to "
                f"{merged.end:,}",
            ),
        )
    )
    return (*_screen(result), *found, *joined, *unread_facts(result.evidence_unread))


def _relatives(result: StrainModelAudit) -> str:
    relatives = result.relatives
    if not relatives.members:
        missing = relatives.missing
        return NONE if missing is None else f"{NONE}: {_NO_RELATIVES[missing]}"
    return listed([f"{m.organism} ({residues(m.length)})" for m in relatives.members])


def _strain_dna(result: StrainModelAudit) -> tuple[Fact, ...]:
    not_read = result.not_read
    if not_read is not None:
        return (
            Fact(label="The strain's DNA over the lost part", value=NOT_READ),
            Fact(label="Why the genome was not read", value=_NOT_READ[not_read]),
        )
    return (
        Fact(
            label="The strain's DNA over the lost part",
            value=LENGTH_SENTENCES[result.dna.verdict],
        ),
        *_dna(result.dna),
    )


def strain_facts(result: StrainModelAudit) -> tuple[Fact, ...]:
    relatives = result.relatives
    median = relatives.median
    tier = relatives.tier
    return (
        Fact(
            label=f"Strain model {result.strain_gene}",
            value=residues(result.strain_length),
        ),
        Fact(
            label=f"Reference model {result.reference_gene}",
            value=residues(result.reference_length),
        ),
        Fact(
            label="Reference residues the strain model lacks",
            value=runs_text(result.lost),
        ),
        Fact(
            label="Strain residues the reference lacks", value=runs_text(result.extra)
        ),
        *_strain_dna(result),
        Fact(label="Related genomes", value=_relatives(result)),
        Fact(
            label="Related genomes from",
            value=NOT_READ if tier is None else TIER_WORDS[tier],
        ),
        Fact(
            label="Median of the related genomes",
            value=NOT_READ if median is None else f"{median:g} residues",
        ),
        Fact(label="Paralogs near the model", value=listed(result.nearby_paralogs)),
        Fact(
            label="Genetic code",
            value=code_text(result.code, inferred=result.code_inferred),
        ),
        *unread_facts(result.evidence_unread),
    )
