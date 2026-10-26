---
type: Backlog
title: A phyletic set is described once
description: veupathdb-py's phyletic expression description repeats a set's genome and species breakdown for every clause over the same set ('at least 139 genomes of Apicomplexa (...) and exactly 139 proteins of Apicomplexa (...)'); describe a set once, release veupathdb-py and veupathdb-mcp, and take both pins.
tags: [orthomcl, veupathdb-py, display]
generated: { by: claude-code/opus-5.5, at: 2026-10-26T00:00:00Z }
status: proposed
---

# A phyletic set is described once

## What happens

TaxaCount.read adds index.span(codes) to every unit and Combination.read joins the readings with nothing recording a set already described. The step editor's StepRationale.tsx also still shows search-ranking scores, which the graph and the appendix no longer show.

## Done when

An expression with two clauses over one set describes its breakdown once; veupathdb-py and veupathdb-mcp are released and pinned; the step editor shows the considered searches by name only.
