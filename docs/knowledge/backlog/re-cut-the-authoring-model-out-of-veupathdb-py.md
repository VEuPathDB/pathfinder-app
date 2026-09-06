---
type: Backlog
title: Re-cut the authoring model out of veupathdb-py
description: veupathdb.domain.strategy ships PathFinder's authoring model inside the VEuPathDB client because veupathdb.wdk imports it; the cut costs 47 measured edges out of the client's call sites.
tags: [veupathdb-py, split, domain, strategy, packaging]
generated: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
status: open
---

# What is wrong

`veupathdb-py` is published as a client for the VEuPathDB WDK and EDA services, and
`veupathdb/domain/strategy/` carries modules that encode PathFinder's authoring model
instead: `operational_spec.py`, `constraints.py`, `spec_diff.py`, `session.py` and
`combination_check.py`. A second consumer of the client would read them as part of the
VEuPathDB contract, which they are not.

# Why they are there

`veupathdb/wdk/**` names them. Measured at the time of the move:

| target | edges from `veupathdb.wdk` |
| --- | ---: |
| `domain.strategy.ast` | 12 |
| `domain.strategy.ops` | 10 |
| `domain.strategy.tree` | 8 |
| `domain.strategy.graph_model` | 7 |
| `domain.strategy.session` | 5 |
| `domain.strategy.operational_spec` | 5 |

# What the work is

Make `veupathdb/wdk/**` name only WDK wire shapes, so the authoring model can move back
to `pathfinder.domain.strategy` beside the eight modules that already live there
(`ast_diff`, `constraint_grounding`, `explain`, `revision`, `spec_hydration`,
`spec_to_operations`, `staleness`, `validate`). This is a refactor of the client's call
sites, not a folder move, which is why it was not done during the split. The decision
that accepted it is [the client library is a distribution](../decisions/the-client-library-is-a-distribution.md).
