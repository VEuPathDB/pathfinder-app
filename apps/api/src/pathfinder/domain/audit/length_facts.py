from __future__ import annotations

from typing import Literal

from veupathdb_mcp.audit import (
    Frameshift,
    GeneFusionAudit,
    GeneLengthAudit,
    GenomeSource,
    LengthCheck,
    LengthScreen,
    NoRelatives,
    NotRead,
    ReferenceMiss,
    StrainModelAudit,
    VariantAnswer,
    VariantCalls,
    VariantsUnread,
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

_VARIANT_ANSWERS: dict[VariantAnswer, str] = {
    "ALTERNATE_AT_INDEL_SITE": (
        "The strain's reads differ from the reference at an indel the site does not call "
        "in frame. It is not established that this is the change"
    ),
    "IN_FRAME_INDEL_CALLED": (
        "The strain's reads carry an indel here that the site calls in frame, which "
        "cannot be the change that shifted the frame"
    ),
    "NO_INDEL_CALLED": "The strain's reads are called as the reference at this place",
    "NO_VARIANT_CALLED": (
        "No sample has a variant here, and this does not show the strain was sequenced"
    ),
    "NOT_COVERED": "The strain's reads do not cover the indel site",
    "NO_SAMPLE_MATCHED": "No sample of the site's calls was matched to the strain",
    "CALL_UNREADABLE": "The strain's call here cannot be read as an indel or as none",
    "SAMPLES_DISAGREE": "The samples matched to the strain do not agree",
}
_UNDETERMINED = (
    "The site's calls hold almost no indel in a run this long, so a missing call does "
    "not show whether the strain's reads carry the change"
)
_MISCOUNT = "The assembly likely miscounts the run"
_EQUAL_COUNTS = (
    "The run holds as many bases in both strains, which is evidence against a miscount"
)
_REFERENCE_MISSES: dict[ReferenceMiss, str] = {
    "MODEL_UNREAD": "The reference gene's model could not be read",
    "WINDOW_TOO_LONG": "The reference gene spans more than an audit reads",
    "FLANK_SHORT": "The bases beside the run are too few to place it in the reference",
    "FLANK_MISSING": "The reference gene lacks the bases beside the run",
    "FLANK_REPEATED": (
        "The bases beside the run repeat in the reference gene, so the run cannot be "
        "placed"
    ),
    "EMPTY_SPAN": "The reference gene holds nothing between the bases beside the run",
}
_VARIANTS_UNREAD: dict[VariantsUnread, str] = {
    "NO_REFERENCE_RUN": "Not read, because the run was not placed in the reference",
    "NO_VARIANT_SEARCH": "The site serves no variant search",
    "SEARCH_REFUSED": (
        "The site refused the variant search for this organism, so the calls are unread"
    ),
    "TOO_MANY_VARIANTS": (
        "More variants lie here than an audit reads, so the finding stands on the DNA "
        "alone"
    ),
}


def _parts(check: LengthCheck) -> str:
    if check.windows == 0:
        return NOT_READ
    counted = [f"{n:,} {_PARTS[label]}" for label, n in check.counts.items()]
    return f"{check.windows:,}: {', '.join(counted)}"


def _from_genome(source: GenomeSource) -> str:
    return f"from the {source.site} genome of {source.organism}"


def _change(shift: Frameshift) -> str:
    strand = "plus" if shift.strand == "+" else "minus"
    bases = "base" if abs(shift.shift) == 1 else "bases"
    return (
        f"{shift.source.site} genome {shift.source.organism}, {shift.source.seqid} bases "
        f"{shift.start:,} to {shift.end:,} ({strand} strand), "
        f"frame {shift.frame_before + 1} to frame {shift.frame_after + 1}, a shift of "
        f"{shift.shift:+d} {bases} against the reference protein's spacing"
    )


def _reference_protein(shift: Frameshift, gene: str | None) -> str:
    first, last = shift.reference_residues
    return f"{known(gene)}, residues {first} to {last}"


def _run(shift: Frameshift) -> str:
    run = shift.run
    if run is None:
        return NONE
    return (
        f"{run.bases} bases of {run.unit}, {shift.source.seqid} {run.start:,} to "
        f"{run.end:,}, {_from_genome(shift.source)}"
    )


def _reference_run(shift: Frameshift) -> str:
    run = shift.reference_run
    if run is not None:
        return (
            f"{run.bases} bases in {run.gene}, {run.source.seqid} {run.start:,} to "
            f"{run.end:,}, {_from_genome(run.source)}"
        )
    if shift.reference_unread is not None:
        return _REFERENCE_MISSES[shift.reference_unread]
    return "No reference strain was compared"


def _said_of_the_calls(shift: Frameshift, calls: VariantCalls) -> str:
    said = (
        _UNDETERMINED
        if calls.answer in {"NO_INDEL_CALLED", "IN_FRAME_INDEL_CALLED"}
        and not calls.determinable
        else _VARIANT_ANSWERS[calls.answer]
    )
    if shift.reads_show_miscount:
        return f"{said}. {_MISCOUNT}"
    if shift.run_counts_equal:
        return f"{said}. {_EQUAL_COUNTS}"
    return said


def _frame_effects(calls: VariantCalls) -> str:
    effects = "; ".join(
        f"{variant}: {'not served' if effect is None else effect}"
        for variant, effect in calls.frame_effects.items()
    )
    return f", indel_frame_effect {effects}" if effects else ""


def _strain_reads(shift: Frameshift) -> str:
    calls = shift.variant_calls
    if calls is None:
        if shift.variants_unread is None:
            return NOT_READ
        return _VARIANTS_UNREAD[shift.variants_unread]
    return (
        f"{_said_of_the_calls(shift, calls)}. {calls.site} {calls.record_type} search "
        f"{calls.search} for {calls.organism} over {calls.seqid} {calls.start:,} to "
        f"{calls.end:,}, table {calls.table}, samples {listed(calls.samples)}, variants "
        f"{listed(calls.variants)}{_frame_effects(calls)}"
    )


def _frameshift(shift: Frameshift, gene: str | None) -> tuple[Fact, ...]:
    return (
        Fact(label="Frame change", value=_change(shift)),
        Fact(label="Reference protein", value=_reference_protein(shift, gene)),
        Fact(label="Run at the change", value=_run(shift)),
        Fact(label="Same run in the reference strain", value=_reference_run(shift)),
        Fact(label="Strain's reads at the run", value=_strain_reads(shift)),
    )


def _dna(check: LengthCheck, reference_gene: str | None) -> tuple[Fact, ...]:
    ns = check.ns_in_window
    return (
        Fact(label="Parts of the reference protein", value=_parts(check)),
        *(
            fact
            for shift in check.frameshifts
            for fact in _frameshift(shift, reference_gene)
        ),
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
        *_dna(result, result.reference_gene),
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
        *_dna(result.dna, result.reference_gene),
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
