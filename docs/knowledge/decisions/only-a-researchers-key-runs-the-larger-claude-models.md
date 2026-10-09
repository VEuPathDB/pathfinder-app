---
type: Decision
title: Only a researcher's key runs the larger Claude models, and the catalog prices the Claude models the meter charges
description: The Anthropic lineup is Claude Haiku 5.5, Sonnet 5.5 and Opus 5.5. The deployment's key runs Haiku 5.5 alone; a researcher's live Anthropic key runs all three. Each catalog entry says whether the deployment may pay for it, the flag fails closed, and the server refuses a turn that names a model nobody may pay for before any provider call. The Claude entries carry their own prices, which the runtime meters per request in place of its price snapshot. Swapping the model silently, billing the deployment, a per-provider rule, and metering every entry at catalog prices were rejected.
tags: [models, quota, pricing, security, settings]
generated: { by: claude-code/opus-5-5, at: 2026-10-08T00:00:00Z }
verified: { by: claude-code/opus-5-5, at: 2026-10-08T00:00:00Z }
status: stable
---

# What was decided

**The lineup.** `platform/model_catalog.py` holds `anthropic:claude-haiku-5-5`
(rank `small`, the provider default), `anthropic:claude-sonnet-5-5` (`standard`)
and `anthropic:claude-opus-5-5` (`flagship`); Claude Haiku 4.5 is gone. The
deployment's Anthropic key lists all three at `GET /v1/models`, and
`GET /v1/models/{id}` reports for each a context window (`max_input_tokens`) of
1,000,000 and an output cap of 128,000 tokens. The attachment probe accepted one
PNG and one PDF on each, and read the PDF's word back
([An attachment is a file part the model can read](an-attachment-is-a-file-part-the-model-can-read.md)).

**Who may pay.** `ModelEntry.deployment_may_pay` is `False` unless the entry says
otherwise. Every OpenAI and Google entry, Haiku 5.5, the mock and each local
model say `True`; Sonnet 5.5 and Opus 5.5 do not. A model id the catalog does
not hold is not one the deployment pays for
(`model_catalog.deployment_may_pay`). `validate_lineup` holds one default and
one small entry per provider both in its whole lineup and in the part the
deployment pays for, so the default of a provider is always one the deployment
runs.

**Where it is enforced.** `platform/model_keys.py::require_deployment_pays`
raises `OwnKeyRequiredError` (422 `OWN_KEY_REQUIRED`) for a model the deployment
may not pay for. `deployment_model` calls it before it builds a provider, so the
injection judge, and every turn model that falls to the deployment's key through
`keyed_model` (the Lead, each sub-agent, site help, the thread title and the
notes compaction), is refused before a request leaves. The chat gate
(`services/provider_keys.py::require_payers`, which `require_turn_paid` and
`jobs/turn_keys.py` call) refuses a request body whose per-role picks name such
a model with no live researcher key for its provider, before the message is
stored or a job is deferred. A researcher's live Anthropic key pays for all three.

**What the researcher sees.** `/api/v1/models` serves a model with
`enabled: false` when its provider holds no deployment key or its entry runs
only on a researcher's key. The web reads the researcher's payers
(`lib/models/payers.ts::selectable`): a model is offered when the researcher's
key pays for its provider, or when the deployment pays and may pay for it. The
model catalog marks a model it holds back "needs your key".

**Tiers.** `platform/tiers.py` derives two preset sets from the ranks:
`TIER_PRESETS` from the entries the deployment pays for, and
`OWN_KEY_TIER_PRESETS` from the whole catalog. `GET /api/v1/tiers` serves both
(`presets`, `ownKeyPresets`), and the settings page applies the own-key set for
a provider the researcher's key pays for. On the deployment's key every
Anthropic tier runs Haiku 5.5; on a researcher's key, quality runs Opus 5.5 and
Sonnet 5.5, balanced Sonnet 5.5 and Haiku 5.5, default and fast Haiku 5.5. The
server's own defaults read `TIER_PRESETS` alone, so a turn with no pick never
names a model the deployment cannot pay for.

**Prices.** From Anthropic's pricing page
(`https://platform.claude.com/docs/en/about-claude/pricing.md`, read
2026-10-08), per 1M tokens:

| model | input | cache read | 5m cache write | output |
|---|---|---|---|---|
| Claude Opus 5.5 | $4.00 | $0.20 | $5.00 | $20.00 |
| Claude Sonnet 5.5 | $2.00 | $0.10 | $2.50 | $10.00 |
| Claude Haiku 5.5, prompt up to 100,000 tokens | $0.10 | $0.01 | $0.125 | $0.50 |
| Claude Haiku 5.5, prompt over 100,000 tokens | $0.50 | $0.05 | $0.625 | $2.50 |

The packaged price snapshot (`genai-prices` 0.1.9) has no Haiku 5.5, and it
matches `claude-sonnet-5-5` to Sonnet 5, whose cache read is $0.20. So each
Claude entry carries a `meter` (`CatalogMeter`: the cache-write price and, for
Haiku, the long-prompt prices), and `install_catalog_prices` installs every
metered entry into the runtime (`assistant_core.pricing.install_model_prices`)
in the api, the worker and the chat debugger at start. The runtime prices each
request from it, so a long-prompt price holds per request and not per run, and
the spend meter, the quota rows and `/api/v1/models` read one number. An entry
with no `meter` (every OpenAI and Google entry) is metered by the snapshot,
which carries those providers' long-prompt tiers and dated price changes.
`PRICES_AS_OF` is 2026-10-08.

**The request surface.** The packaged pydantic-ai profile (2.54) knows that
Sonnet 5.5 and Opus 5.5 are never forced to a tool, and does not know Haiku 5.5:
it sends Haiku a token-budget thinking setting, which the API refuses with a 400
at every effort. The runtime's `assistant_core.models.claude_profiles.ClaudeProvider`
lays Haiku 5.5's measured surface over the packaged profile and leaves every
other model on it, and `model_keys.build_provider` builds every Anthropic model
on it.

# What was rejected

- **Running Haiku in place of a Sonnet or Opus pick without a key.** The
  researcher would read an answer from a model they did not choose.
- **Billing the deployment for a pick the researcher made.** The deployment's
  allowance is sized for Haiku; one Opus turn costs forty times as much.
- **A per-provider payer rule.** It cannot say that the deployment pays for one
  Anthropic model and not another.
- **A flag that defaults to the deployment paying.** A model added later would
  be billed to the deployment by omission.
- **Metering every entry at catalog prices.** The snapshot carries the OpenAI
  and Google long-prompt tiers and a scheduled Gemini price change, which three
  headline prices per entry cannot express.
- **Pricing a run from its summed tokens.** A run of several requests passes
  100,000 input tokens long before any one prompt does, and would be charged
  five times Haiku's price for every token.

# Where it lives

`platform/model_catalog.py`, `platform/model_keys.py`, `platform/tiers.py`,
`platform/errors.py`, `services/provider_keys.py`,
`transport/http/routers/models.py`, `transport/http/routers/tiers.py`,
`ai/graph/_lead_capture.py`, and in the web `lib/models/payers.ts`,
`features/settings/tierPresets.ts`,
`features/settings/components/ModelCatalogModal.tsx`. In the runtime
`assistant_core/pricing.py`, `assistant_core/cost.py` and
`assistant_core/models/claude_profiles.py`
(`assistant-platform: docs/knowledge/decisions/a-host-prices-its-own-models.md`).
