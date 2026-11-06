---
type: Backlog
title: Explore's stop reply names its own stage
description: When Explore's model never answers, the stop reply reuses the Lead's wording and names the Lead's settings stage; fix it when the explore role joins the settings picker, with a stage label parameter in _lead_stops.py and Build's output unchanged.
tags: [modes, explore, settings, stop-reply]
generated: { by: claude-code/opus-5.5, at: 2026-11-06T00:00:00Z }
status: proposed
---

# Explore's stop reply names its own stage

## What is known

An Explore turn that ends on a run error writes `fallback_prose` (`ai/graph/_lead_stops.py`).
When the model is in the catalog and never answered, that text reads "The Assistant stage of
this turn runs <model>", with a hint to change that stage in Settings. The label comes from
`_STAGE_LABELS` through `_stage_that_did_not_answer`, which labels the run as the Lead's.
Explore's model is set under its own role, `explore`, so the hint points at a stage that does
not run Explore.

The explore role is not on the Settings picker yet (`PICKABLE_ROLE_DESCRIPTIONS` in
`apps/web/src/lib/models/phaseRoles.ts`), so no stage the researcher can change runs Explore
today.

## What to do

When the explore role joins the picker:

1. Give the stop path a stage label parameter, so Explore passes its own label ("Exploring",
   `PHASE_LABELS.explore`).
2. Pin Build's stop replies byte for byte before and after.
3. Add a test of Explore's error stop with a catalogued model that never answers.

## Done when

Explore's stop reply names the Explore stage, and every Lead stop reply is unchanged.
