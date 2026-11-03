---
type: Backlog
title: A short model names the frameshift that cut it
description: The frameshift verdict, its error type and its words are written against the unreleased library; what remains is the veupathdb-mcp release, the pin, one recording of the indel attributes, and the NF54 audit rerun that shows the finding.
tags: [audit, length, frameshift, assembly, veupathdb-mcp]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: proposed
---

# A short model names the frameshift that cut it

The decision is
[a frameshift finding names the sequence and not the cause](../decisions/a-frameshift-finding-names-the-sequence-and-not-the-cause.md).

## What remains

1. Release veupathdb-mcp with `FRAMESHIFT` and take the pin.
2. Record a `variation` record with its `indel_*` attributes on QA plasmodb, to learn whether
   the site serves an indel's length. The `VariantStrains` table does not, so a call is not
   compared with the shift yet.

## Done when

A rerun of the NF54 audit reports PfNF54_040013300 as a frameshift at the poly-A run, with
29 A in NF54 against 28 in 3D7, and not as an annotation truncation.
