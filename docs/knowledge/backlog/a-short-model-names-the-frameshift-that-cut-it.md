---
type: Backlog
title: A short model names the frameshift that cut it
description: The frameshift verdict, its error type and its words are written against the unreleased library; what remains is the veupathdb-mcp release, the pin, one recording of the variant search, and the NF54 audit rerun that shows the finding.
tags: [audit, length, frameshift, assembly, veupathdb-mcp]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: proposed
---

# A short model names the frameshift that cut it

The decision is
[a short model is a frameshift in the assembly](../decisions/a-short-model-is-a-frameshift-in-the-assembly.md).

## What remains

1. Release veupathdb-mcp with `FRAMESHIFT` and take the pin.
2. Record one `VariantsByLocation` report and one `VariantStrains` record from QA plasmodb,
   and replace the library test's reconstructed bodies with them. The test's field names and
   values come from a saved QA run; no raw body is in the fixtures.

## Done when

A rerun of the NF54 audit reports PfNF54_040013300 as a frameshift at the poly-A run, with
29 A in NF54 against 28 in 3D7, and not as an annotation truncation.
