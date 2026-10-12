---
type: Backlog
title: A join under a saved-strategy branch is not measured
description: A combine added above a step that is the secondary input of a combine carrying expanded_strategy_id may land inside the nested saved strategy on the site; no test or live run has measured where it lands.
tags: [eda, strategy, operations, saved-strategy]
generated: { by: claude-code/opus-5.5, at: 2026-10-12T00:00:00Z }
status: proposed
---

# A join under a saved-strategy branch is not measured

An export joins the built part of its branch with an added step, a combine over
the joined step and the export, and a rewire of the joined step's consumer
(`ai/tools/standalone/_eda_step_write.py::join_write`). An edit that adds a
criterion beside a held step emits the same pair
(`domain/strategy/spec_to_operations.py::_join`).

When the joined step is the secondary input of a combine that carries
`expanded_strategy_id`, the tree conversion (`domain/strategy/spec_tree.py::_combine`)
reads that input as a nested strategy. No operation moves the mark, so the new
combine may be written inside the nested strategy. The counts would be right
and the grouping on the site wrong. This is a reading of the code, with no
measured tree.

**To do.** Insert a saved strategy, join an export and an edit-added criterion
to a step inside it, read the WDK step tree, and write the six headings from
what the site returns. Fix where the mark is carried if the grouping is wrong.
