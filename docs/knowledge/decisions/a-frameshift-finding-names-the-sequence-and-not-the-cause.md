---
type: Decision
title: A frameshift finding names the sequence and not the cause
description: The library's FRAMESHIFT and OTHER_FRAME verdicts map to their own error types at medium certainty, never to truncated_model, and the finding states what the site served as facts with their sources; it concludes no cause from served calls.
tags: [audit, findings, frameshift]
status: stable
---

# The choice

`domain/audit/findings.py` maps a `SHORT` gene with the verdict `FRAMESHIFT` to
`sequence_frameshift`, and `OTHER_FRAME` to `part_in_other_frame`, both at medium certainty. A
strain check whose genome answers either judges no side and names the same error, with the
model role `strain`. Only `GENOME_ENCODES`, the missing part in the model's open frame, stays
`truncated_model`.

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
