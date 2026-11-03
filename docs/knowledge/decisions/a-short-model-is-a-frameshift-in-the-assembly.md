---
type: Decision
title: A short model cut by a frameshift is an error of the assembly
description: The library's FRAMESHIFT verdict maps to its own error type, assembly_frameshift, at medium certainty, and a strain's FRAMESHIFT names the same error on the strain's model; it is not a truncated_model, and it says the assembly likely miscounts a run only when the strain's own variant calls can show that.
tags: [audit, findings, frameshift, assembly]
status: stable
---

# The choice

`domain/audit/findings.py` maps a `SHORT` gene with the verdict `FRAMESHIFT` to
`assembly_frameshift` at medium certainty. A strain check whose genome answers `FRAMESHIFT`
judges no side and names the same error, with the model role `strain`. The words say the
model follows the assembly.

The certainty is medium because the DNA shows the frame change and not its cause: an
assembly error and a real mutation read alike in one genome.

The facts of the finding (`domain/audit/length_facts.py`) name the genome span and frames,
the run, the same run in the reference strain, and the site's variant calls, each with the
site, genome, gene, search, table and record ids it was read from. They say the assembly
likely miscounts the run only when the calls show no indel and `determinable` is true. Over a
long homopolymer the site's calls hold almost no indel, so there a missing call makes no
claim.

The library's half is `veupathdb-mcp: docs/knowledge/decisions/a-short-model-names-the-frameshift-that-cut-it.md`.

# What was rejected

**`truncated_model` with a note.** The run's tallies and synthesis read the error type, so
assembly errors would still count and read as annotation truncations.

**High certainty, as `truncated_model` has.** That rating would state the cause, which the
window does not show.
