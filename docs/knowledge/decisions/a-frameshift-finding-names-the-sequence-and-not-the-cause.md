---
type: Decision
title: A frameshift finding names the sequence and not the cause
description: The library's FRAMESHIFT and OTHER_FRAME verdicts map to their own error types at medium certainty, sequence_frameshift, possible_missed_exon or part_in_other_frame, never to truncated_model, and the finding states what the site served as facts with their sources; it concludes no cause from served calls.
tags: [audit, findings, frameshift]
status: stable
---

# The choice

`domain/audit/findings.py` maps a `SHORT` gene with the verdict `FRAMESHIFT` to
`sequence_frameshift` at medium certainty. `OTHER_FRAME` maps to `possible_missed_exon` when a
splice pair sits at every jump of the track, listed or past the cap, else to `part_in_other_frame`,
both at medium certainty. Only `GENOME_ENCODES`, the missing part in the model's open frame, stays
`truncated_model`: high certainty when the reading frame holds, medium otherwise. The reading frame
holds when the frame is open across every placed window beyond the model and every jump keeps the
frame with no splice pair. A stop in the part or a window in another frame is stated as a fact. A jump with a pair may be an intron, in
frame or not, so it lowers the certainty and is stated. A jump that keeps the frame with no pair is
stated and lowers nothing. A jump past the cap counts the same and is stated by its shift and pair.

`possible_missed_exon` says "may": the missing part lies across a splice pair. A pair is not proof.
On random sequence, for a stretch of 30 to 300 bases at the library's slack of 6 bases, a pair sits at
one change by chance 9.3% of the time at 80% A+T and 24% at 60% A+T; taking changes as independent,
0.87% and 5.8% at two changes, and 0.08% and 1.4% at three.

A strain's side is judged from its relatives whatever frame the part is in. `REFERENCE_LONG` still
names the reference. A `FRAMESHIFT` names `sequence_frameshift`. `STRAIN_SHORT` with `OTHER_FRAME`
follows the same rule and does not name `truncated_model`, because of what a curator does next:
`truncated_model` says extend the model through open DNA, and a part in another frame cannot be
reached that way. `possible_missed_exon` gives them the next step, adding an exon, with the pair,
position and shift as facts.

The certainty is medium because the DNA shows where the frame changes and not why: an assembly
error, a real mutation and a missed exon can read alike in one genome.

The facts of a finding (`domain/audit/length_facts.py`) state, for each change, the site, genome,
span and frames, the reference protein's gene and residues, the splice pair at the change, the
run, the same run in the reference strain or why it was not placed, and whether the two counts
differ by the shift. They state each variant record at that place with its `variant_type`,
`indel_ref_allele` and `indel_frame_effect` as served, and each matched sample's genotype, allele,
depth and read frequency, with the search, organism, range and table they were read from. A
mismatch of the counts is stated as a mismatch, because flanks can land in different copies of a
repeat. "No sample was matched", "the search was refused" and "too many variants" are stated as
they are. Over a homopolymer of 7 or more bases with no indel record, the facts add that the
served calls say little there.

The library's half is `veupathdb-mcp: docs/knowledge/decisions/a-short-model-names-the-frameshift-that-cut-it.md`.

# What was rejected

**Concluding a cause from served calls.** "The assembly likely miscounts the run" and "this indel
cannot be the change" read a cause out of a record. `indel_frame_effect` is one value per site and
nothing links a sample's row to it: on `Variant_Pf3D7_01_v3_283234`, sample `RV_3630` has genotype 1
and allele `A`, which is not the base that site's deletion leaves. An SNV row shows coverage at
that base and nothing about indels. So the facts state the records and draw nothing from them.

**Treating a rejected frame change as a truncation.** Each guard that rejected a frame change sent
it to `truncated_model` at high certainty, which says the part lies in the model's reading frame.
It does not. A part on another diagonal has its own outcome.

**`truncated_model` with a note.** The run's tallies and synthesis read the error type, so these
would still count and read as annotation truncations.

**`assembly_frameshift`.** It names a cause.

**High certainty, as `truncated_model` has.** That rating would state the cause, which the window
does not show.
