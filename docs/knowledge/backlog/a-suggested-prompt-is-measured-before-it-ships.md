---
type: Backlog
title: A suggested prompt is measured before it ships
description: Suggested questions come from biologists and ship only after a measured run; the OrthoMCL single-copy suggestion builds the 2-group phyletic strategy on QA, but no suggestion has a recorded pass and nothing withholds one that fails.
tags: [suggested-prompts, orthomcl, first-run]
generated: { by: claude-code/opus-5, at: 2026-10-20T00:00:00Z }
status: proposed
---

# A suggested prompt is measured before it ships

## What happens

`apps/web/src/features/conversation/data/suggestedQuestions.json` offers on OrthoMCL
"List single-copy ortholog groups across the apicomplexans." The turn binds
`GroupsBySingleCopy` with the site defaults (all taxa 4 to 20, core 2 to 10,
peripheral 2 to 10), returns 8,699 groups, and VERIFY reports that no
Apicomplexa-only filter is encoded. The search has no clade parameter; the correct
query is a phyletic expression requiring every apicomplexan species with one copy
each (`APIC=<N>T AND APIC=<N>`).

## Depends on

Two `veupathdb-mcp` changes (its backlog): a clade code names its species count, and
Single Copy Orthogroups says it cannot name a clade.

## Change

1. Reword the suggestion so it has one reading: exactly one protein from every
   apicomplexan species.
2. Run every suggested prompt once on its site and keep only those whose strategy
   VERIFY reports as meeting each explicit constraint; record the run in the log.
3. Biologists propose the example questions: each site's candidates live in one
   reviewable file with the question, the answer a biologist expects (the record type,
   the constraints, roughly how many results), and who may edit it. Each candidate
   becomes an eval case (`evals/corpus/`) and is offered only after its recorded run
   meets the stated expectation; a candidate that fails stays in the file with its
   measured outcome, so the proposer sees why.

## Where it stands

The two `veupathdb-mcp` changes shipped in 0.2.0b35. Replayed on QA OrthoMCL with Luna
(corpus case `orthomcl-single-copy-across-the-apicomplexans`), the unchanged suggestion
builds `GroupsByPhyleticPattern` `APIC=139T AND APIC=139` and returns 2 groups (again on 2026-11-02, with the genome breakdown shown once). Every
suggestion was run once on 2026-10-31, but no pass or fail is recorded per suggestion and
nothing withholds one that fails. Steps 1, 2 and 3 remain.

## Done when

The OrthoMCL suggestion builds a phyletic-pattern strategy restricted to the
apicomplexan species, every offered suggestion has a recorded passing run, and a
biologist can add a candidate without a code change.
