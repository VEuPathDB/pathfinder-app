---
type: Backlog
title: A phyletic set is described once
description: veupathdb-py describes a phyletic set's genome and species breakdown once per expression on its branch fix/describe-a-set-once; release veupathdb-py, release veupathdb-mcp pinning it, and take both pins.
tags: [orthomcl, veupathdb-py, display]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: proposed
---

# A phyletic set is described once

## What happens

The pinned veupathdb-py repeats a set's genome and species breakdown after every unit over that set, so "APIC>=139T AND APIC=139" reads with "(139 genomes of 74 species; ...)" twice. The fix is on veupathdb-py's branch `fix/describe-a-set-once`: the reading of an expression records each genome set it has described and names the breakdown on the first unit over it only. veupathdb-mcp needs no code change.

## Done when

veupathdb-py is released with the fix, veupathdb-mcp is released with a pin on that release, and PathFinder takes both pins.
