---
type: Backlog
title: A tier preset is four required phase roles, so a one-agent assistant cannot be tiered
description: TierPreset declares lead, frame, execution and verification as required fields and repeats the same four names in for_role, so site_help runs on a compile-time model whatever tier the user picks, and GET /api/v1/tiers serves PathFinder's phase shape to every client.
tags: [models, tiers, assistants, site-help, generality]
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
status: stable
---

# What I did

Read `apps/api/src/pathfinder/ai/models/tiers.py` (165 lines) and followed
`resolve_phase_tier_config` to every caller, then read how the second assistant
picks its model.

# What I got

`tiers.py:45-49` declares the preset as four required fields:

```
lead: PhaseTierConfig
frame: PhaseTierConfig
execution: PhaseTierConfig
verification: PhaseTierConfig
```

and `for_role` (lines 50-58) rebuilds the same four names as a dictionary
literal, so the role set is written twice in one class.
`resolve_phase_tier_config` has two callers, `ai/graph/_lead_model.py:34` and
`ai/lead/sub_agent_tools.py:162`, both PathFinder phases.
`assistants/site_help/agent.py:130-134` picks its model with
`_model()`, which returns the mock model or the module constant
`SITE_HELP_MODEL` and consults no tier. `transport/http/routers/tiers.py:19`
serves `TIER_PRESETS` as the wire shape of a tier.

# Why that's wrong

The tier is the user's one control over what a turn costs. A researcher who
selects the budget tier still runs the second assistant on whatever model its
source file names, and the settings screen gives no hint that the control does
not reach it. Any new assistant has the same hole, and a client reading
`GET /api/v1/tiers` learns four role names that only PathFinder has.

# Why it happens

`TierPreset` models a tier as PathFinder's four phase roles rather than as a
mapping from a role name to its configuration.

# Fix

In this repository. Make the preset a mapping, `roles: dict[str,
PhaseTierConfig]`, so `for_role` is one lookup and the four presets keep their
four entries; add the site-help role to each preset and resolve
`SITE_HELP_MODEL` through `resolve_phase_tier_config` with the provider and
tier the turn carries. The response shape changes, so run
`yarn generate:types` and update the settings screen that renders the presets.

# What you'd get

Picking a tier moves every assistant's model, a new assistant adds one entry
per preset instead of a field on a shared model, and the role names on the wire
are data rather than a schema every client must match.
