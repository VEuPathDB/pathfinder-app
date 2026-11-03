---
type: Backlog
title: A short model names the frameshift that cut it
description: The FRAMESHIFT and OTHER_FRAME verdicts, their error types and their facts are written against the unreleased library; what remains is the veupathdb-mcp release, the pin, and the NF54 audit rerun that shows the finding.
tags: [audit, length, frameshift, assembly, veupathdb-mcp]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: proposed
---

# A short model names the frameshift that cut it

The decision is
[a frameshift finding names the sequence and not the cause](../decisions/a-frameshift-finding-names-the-sequence-and-not-the-cause.md).

## What remains

1. Release veupathdb-mcp with `FRAMESHIFT` and take the pin.

## Done when

A rerun of the NF54 audit reports PfNF54_040013300 as `FRAMESHIFT` at the poly-A run, with 29
against 28 stated as a fact, and not as an annotation truncation. A part in the model's open
frame still reads as a truncation.
