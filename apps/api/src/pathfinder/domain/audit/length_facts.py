from __future__ import annotations

from typing import Literal

from veupathdb_mcp.audit import (
    FrameChange,
    GeneFusionAudit,
    GeneLengthAudit,
    GenomeSource,
    LengthCheck,
    LengthScreen,
    NoRelatives,
    NotRead,
    ReferenceMiss,
    StrainCall,
    StrainModelAudit,
    VariantSite,
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
    "FEWER_THAN_TWO": (
        "fewer than two genomes of other species in this genus, and fewer than two "
        "in other genera, have a length for the gene"
    ),
}
_NOT_READ: dict[NotRead, str] = {
    "NO_LOST_RUN": "The strain protein lacks no run of the reference protein",
    "UNQUALIFIED": "The ortholog group is a residual group",
    "PARALOG_IN_WINDOW": "A paralog lies in the region the check reads",
}

_CALLS_SAY_LITTLE = (
    "The site's calls hold almost no indel in a run this long, so they say little here"
)
_NO_SAMPLE = "No sample of the site's calls was matched to the strain"
_NO_RECORD = "The search holds no variant record here"
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


def _change(change: FrameChange) -> str:
    strand = "plus" if change.strand == "+" else "minus"
    bases = "base" if abs(change.shift) == 1 else "bases"
    return (
        f"{change.source.site} genome {change.source.organism}, {change.source.seqid} "
        f"bases {change.start:,} to {change.end:,} ({strand} strand), "
        f"frame {change.frame_before + 1} to frame {change.frame_after + 1}, a shift of "
        f"{change.shift:+d} {bases} against the reference protein's spacing"
    )


def _reference_protein(change: FrameChange, gene: str | None) -> str:
    first, last = change.reference_residues
    return f"{known(gene)}, residues {first} to {last}"


def _run(change: FrameChange) -> str:
    run = change.run
    if run is None:
        return NONE
    return (
        f"{run.bases} bases of {run.unit}, {change.source.seqid} {run.start:,} to "
        f"{run.end:,}, {_from_genome(change.source)}"
    )


def _splice_pair(change: FrameChange) -> str:
    pair = change.splice_pair
    if pair is None:
        return NONE
    return (
        f"{pair.motif}, bases {pair.donor:,} to {pair.acceptor:,} of "
        f"{change.source.seqid}"
    )


def _reference_run(change: FrameChange) -> str:
    run = change.reference_run
    if run is not None:
        return (
            f"{run.bases} bases in {run.gene}, {run.source.seqid} {run.start:,} to "
            f"{run.end:,}, {_from_genome(run.source)}"
        )
    if change.reference_unread is not None:
        return _REFERENCE_MISSES[change.reference_unread]
    return "No reference strain was compared"


def _run_counts(change: FrameChange) -> str:
    run, reference = change.run, change.reference_run
    if run is None or reference is None:
        return "Not compared"
    fits = "matches" if change.counts_match_shift else "does not match"
    return (
        f"{run.bases} here against {reference.bases} in the reference strain, a "
        f"difference of {run.bases - reference.bases}, which {fits} the shift of "
        f"{change.shift:+d}"
    )


def _served(value: str | None) -> str:
    return "not served" if value is None else value


def _call(call: StrainCall) -> str:
    return (
        f"{call.sample} genotype {call.genotype}, allele {_served(call.allele)}, "
        f"depth {_served(call.depth)}, read frequency {_served(call.read_frequency)}"
    )


def _site(site: VariantSite) -> str:
    calls = "; ".join(_call(call) for call in site.calls)
    return (
        f"{site.variant}: variant_type {_served(site.variant_type)}, indel_ref_allele "
        f"{_served(site.indel_ref_allele)}, indel_frame_effect "
        f"{_served(site.indel_frame_effect)}{'; ' + calls if calls else ''}"
    )


def _strain_reads(change: FrameChange) -> str:
    calls = change.variant_calls
    if calls is None:
        if change.variants_unread is None:
            return NOT_READ
        return _VARIANTS_UNREAD[change.variants_unread]
    said = [
        (
            f"{calls.site} {calls.record_type} search {calls.search} for "
            f"{calls.organism} over {calls.seqid} {calls.start:,} to {calls.end:,}, "
            f"table {calls.table}"
        ),
        *(_site(site) for site in calls.sites),
    ]
    if not calls.sites:
        said.append(_NO_RECORD)
    elif not calls.samples:
        said.append(_NO_SAMPLE)
    if calls.calls_say_little:
        said.append(_CALLS_SAY_LITTLE)
    return ". ".join(said)


def _reading_frame(change: FrameChange) -> str:
    if not change.keeps_frame:
        return "The reading frame changes"
    if change.splice_pair is None:
        return "The reading frame holds"
    return "The part lies across a splice pair in the same frame"


def _frame_change(change: FrameChange, gene: str | None) -> tuple[Fact, ...]:
    return (
        Fact(label="Frame change", value=_change(change)),
        Fact(label="Reading frame at the change", value=_reading_frame(change)),
        Fact(label="Reference protein", value=_reference_protein(change, gene)),
        Fact(label="Splice pair at the change", value=_splice_pair(change)),
        Fact(
            label="Model past the change",
            value=(
                "The model goes on past this change"
                if change.model_goes_on
                else "The model holds nothing past this change"
            ),
        ),
        Fact(label="Run at the change", value=_run(change)),
        *(
            (
                Fact(
                    label="Same run in the reference strain",
                    value=_reference_run(change),
                ),
                Fact(label="Run counts", value=_run_counts(change)),
                Fact(label="Strain's reads at the run", value=_strain_reads(change)),
            )
            if change.run_explains_shift
            else ()
        ),
    )


def _unlisted(changes: list[FrameChange]) -> tuple[Fact, ...]:
    if not changes:
        return ()
    said = [
        f"a shift of {change.shift:+d} at "
        f"{change.splice_pair.motif if change.splice_pair else 'no splice pair'}"
        for change in changes
    ]
    return (
        Fact(
            label="Changes past those listed, not read further",
            value=f"{len(changes)}: {', '.join(said)}",
        ),
    )


def _part(check: LengthCheck) -> tuple[Fact, ...]:
    if check.verdict != "GENOME_ENCODES":
        return ()
    stop = check.part_stop
    frame = (
        f"A stop at base {stop:,}"
        if stop is not None
        else "Open across every placed window"
        if check.part_open
        else "Not open across every placed window"
    )
    return (
        Fact(label="Model's frame across the part", value=frame),
        *(
            (Fact(label="Unknown bases in the part", value=f"{check.ns_in_part:,}"),)
            if check.ns_in_part
            else ()
        ),
    )


def _dna(check: LengthCheck, reference_gene: str | None) -> tuple[Fact, ...]:
    ns = check.ns_in_window
    return (
        Fact(label="Parts of the reference protein", value=_parts(check)),
        *(
            fact
            for shift in check.frame_changes
            for fact in _frame_change(shift, reference_gene)
        ),
        *_unlisted(check.unlisted_changes),
        *_part(check),
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
