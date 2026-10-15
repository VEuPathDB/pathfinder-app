---
type: Backlog
title: A stated record type is compared by its words
description: FRAME's bind of an OrthoMCL group search is refused because the researcher's words for the record type, "ortholog groups", are compared to the record type's name, "group".
tags: [frame, record-type, orthomcl]
generated: { by: claude-code/opus-5.5, at: 2026-10-15T00:00:00Z }
status: proposed
---

# A stated record type is compared by its words

## What I did

One turn on the QA OrthoMCL site, three pasted proteins: "I sequenced a new genome.
Map these proteins to OrthoMCL ortholog groups and tell me which group each one lands in."

## What I got

FRAME bound a `ByBlast` criterion per protein, then each `GroupsFromSequences` bind was
refused once:

> c_prot1_groups: GroupsFromSequences returns group, not Ortholog groups.

The next call bound all three ("set to GroupsFromSequences, returns group"), and the
turn answered with each protein's groups.

## Why that's wrong

The search returns exactly the ortholog groups the researcher asked for. The refusal
costs three model calls and a retry, and a pass that believes it could drop the step.

## Why it happens

Not traced. The refusal reads like the stated record type check comparing the requested
words with the record type's url segment.

## Fix

Compare a stated record type with the record type's display names, as the site lists them.

## What you'd get

The three `GroupsFromSequences` binds go through on the first call.
