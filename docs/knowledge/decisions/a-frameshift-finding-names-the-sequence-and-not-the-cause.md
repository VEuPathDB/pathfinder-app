---
type: Decision
title: A frameshift finding names the sequence and not the cause
description: The library's FRAMESHIFT verdict maps to its own error type, sequence_frameshift, at medium certainty, true whichever way the reads fall; a cause is stated only from evidence, and the site's variant table does not give an indel's length, so no finding says the strain's reads carry this change.
tags: [audit, findings, frameshift]
status: stable
---

# The choice

`domain/audit/findings.py` maps a `SHORT` gene with the verdict `FRAMESHIFT` to
`sequence_frameshift` at medium certainty. A strain check whose genome answers `FRAMESHIFT`
judges no side and names the same error, with the model role `strain`. The words say the model
follows the genome sequence, which is true whichever way the reads fall.

The certainty is medium because the DNA shows the frame change and not its cause: an assembly
error and a real mutation read alike in one genome.

The facts of the finding (`domain/audit/length_facts.py`) name the site, genome, span and
frames, the reference protein's gene and residues, the run, the same run in the reference
strain or why it was not placed, and the variant calls with their search, organism, range,
table, samples and record ids, or why they were not read.

A cause is stated only from evidence. "The assembly likely miscounts the run" appears only when
the library's `readsShowMiscount` holds: a run exists, the reference's count was read and
differs, the strain's reads cover the site, no indel is called, and over a long homopolymer,
where the calls hold almost no indel, that is not taken as evidence. Equal counts are stated as
evidence against a miscount.

No finding says the change is in the strain. The `VariantStrains` table serves one base as the
allele even at an indel site, so a call cannot be compared with the shift; a non-reference call
at an indel site is stated as that and no more.

The library's half is `veupathdb-mcp: docs/knowledge/decisions/a-short-model-names-the-frameshift-that-cut-it.md`.

# What was rejected

**`truncated_model` with a note.** The run's tallies and synthesis read the error type, so these
would still count and read as annotation truncations.

**`assembly_frameshift`.** It names a cause. A non-reference call in the strain's reads would
contradict the error's own title.

**High certainty, as `truncated_model` has.** That rating would state the cause, which the window
does not show.
