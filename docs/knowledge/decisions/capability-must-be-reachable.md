---
type: Decision
title: A capability is not shipped until the model can find it
description: Phase 2b scoring was already built and registered; what was missing was any path from the unscored tool to it, plus a test that it stays reachable.
tags: [agents, experiments, tooling]
generated: { by: claude-code/opus-5, at: 2026-08-09T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-09T00:00:00Z }
status: stable
---

# What was already there

The backlog carried "Phase 2b (controls/MCC scoring) not built". It was built:

- `services/experiment/metrics.py` computes MCC from TP/FP/TN/FN.
- `services/experiment/scored_comparison.py` runs each variant as a scored experiment against a saved control set and ranks by an objective (`mcc`, `balanced_accuracy`, `f1`, `precision`, `sensitivity`).
- `ai/tools/standalone/scored_comparison.py` exposes `compare_variants_scored`, registered on the Lead.
- The frontend renders `DataScoredComparison.tsx`, with tests.

Fourteen tests covered it and passed.

# The real gap

A tool the model never selects is not a shipped capability, and tool descriptions are the only place a Lead learns what exists. `compare_search_variants` said it "does NOT score or pick a winner" and stopped there, never naming the tool that does. A Lead reading it learned scoring was unavailable, not that a scored counterpart was one call away.

It now points at `compare_variants_scored` and says when to prefer each.

# Why reachability gets its own tests

Every unit test of `compare_variants_scored` keeps passing if the `Tool(...)` line is deleted from the Lead. The capability becomes unreachable in production while the suite stays green, which is the worst shape a regression can take.

`TestTheLeadCanReachControlScoring` asserts the tool is registered, that `build_control_set` and `list_control_sets` are registered alongside it (the scored tool takes a `control_set_id`, so it is useless without a way to obtain one), and that the unscored tool still names it. Verified by deleting the registration and confirming the test fails.

# Anchor

`ai/lead/lead_agent.py` tool list and the docstring of `compare_search_variants`. Guarded by `tests/unit/ai/tools/test_scored_comparison.py`.
