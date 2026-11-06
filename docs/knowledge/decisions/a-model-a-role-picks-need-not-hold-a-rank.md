---
type: Decision
title: A model a role picks need not hold a rank
description: A catalog entry may be unranked. An unranked entry is offered in the model catalog and runs when a role picks it, and no tier ever resolves to it, so a newer model is taken without moving the model any tier runs. Replacing a provider's flagship with each new release and waiting until a release earns a rank were rejected.
tags: [models, catalog, tiers, settings]
generated: { by: claude-code/opus-5-5, at: 2026-11-06T00:00:00Z }
status: stable
---

# What was decided

`ModelRank` (`platform/model_entry.py`) is a `TierRank` (`flagship`,
`standard`, `small`) or `unranked`. The tiers are derived from the tier
ranks alone:

- `validate_lineup` counts one entry per tier rank and skips unranked
  entries, so a provider may hold any number of them.
- `derive_tiers` (`platform/tiers.py`) picks only from `TierRank`, so no tier
  resolves to an unranked entry.
- An unranked entry is never its provider's default. The `ModelEntry`
  validator refuses that combination, because the `default` tier runs the
  provider's default entry.

An unranked entry is otherwise an ordinary entry: `GET /api/v1/models`
returns it, the Model Catalog offers it for any role, its prices meter its
runs, and `deployment_may_pay` decides who pays for it.

The first unranked entry is `anthropic:claude-fable-5-1`. Anthropic's own
models overview recommends Claude Opus 5.5 for most workloads and Claude
Fable 5.1 for demanding reasoning, so Opus 5.5 keeps the `flagship` rank and
the quality tier of a researcher's Anthropic key still runs it.

# What was rejected

- **Replacing the flagship with each new release.** A new flagship moves the
  quality tier, and with it the Lead and FRAME of every researcher who picked
  that tier, onto a model no turn of this product has run. A tier is a
  measured choice; a release is not a measurement.
- **Waiting until a release earns a rank.** A researcher with their own key
  could not pick the newer model at all until it displaced an entry, so the
  catalog would trail every provider by the length of a measurement.
