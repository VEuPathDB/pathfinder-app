---
type: Backlog
title: A stored tier derives its explore pick
description: When the explore role joins the settings picker, a tier stored before then holds no explore pick; decide whether it re-applies the tier or follows it, and pin the choice with a vitest.
tags: [modes, explore, settings, tiers, web]
generated: { by: claude-code/opus-5.5, at: 2026-11-06T00:00:00Z }
status: proposed
---

# A stored tier derives its explore pick

## What is known

Every tier preset holds an `explore` role, but the Settings picker does not offer it
(`apps/web/src/lib/models/phaseRoles.ts`). `applyTierPreset` and `deriveActiveTier`
(`apps/web/src/features/settings/tierPresets.ts`) read only the pickable roles, so a saved
tier still reads as that tier and not "Custom".

When the explore role becomes pickable, a researcher's stored settings from before hold no
explore pick. Two readings are possible:

- **Re-apply the tier.** The stored tier is applied again, so explore takes the tier's model.
- **Follow the tier.** An absent pick follows whatever the tier names at send time.

Each gives a different "Custom" result for a stored tier, and a wrong one shows a researcher
"Custom" for settings they never changed.

## What to do

In the change that makes the explore role pickable, choose one reading, implement it in
`tierPresets.ts`, and pin it with a vitest that loads stored settings with no explore pick and
asserts the active tier and the explore model sent.

## Done when

A stored tier without an explore pick reads as that tier, and the test pins which model
explore runs.
