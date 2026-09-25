---
type: TestPlan
title: UAT flows - settings and account
description: The model and the reasoning effort a turn runs on, a researcher's own provider key (added, refused, removed), the usage figures, the data tab, privacy and the local settings.
tags: [uat, flows, settings, models, provider-keys, usage]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: draft
---

# Settings and account (A)

Settings opens from the nav rail (`Settings`, gear) or on the `Model` tab from `AI model settings` (brain). Tabs: `Model`, `Provider keys`, `Data`, `Memory`, `Privacy`, `Advanced`, `Seeding`. Only the OpenAI models are in UAT ([known limits](known-limits.md)).

## A1 - The model a turn runs on - core, once

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Settings, `Model` | Read | `Strategy builder runs each stage below on its own model. ...`; stage rows `Assistant`, `Planning`, `Building`, `Checking`; `Preset` with `Quality`, `Balanced`, `Default`, `Fast`; each unpinned row `Default: <model id>` (the deployment's default; `openai:gpt-5.6-luna` in the measurements) |
| 2 | `Preset` | `Fast`; close Settings; send the S1 prompt in a new conversation | The trace header's usage reads `gpt-5.6-luna (low) - <tokens>, <cost>` |
| 3 | `Preset` | `Default`; send the S1 prompt again | `gpt-5.6-luna (medium) - <tokens>, <cost>` |
| 4 | `Preset` | `Quality`; send the S1 prompt | `gpt-5.6-sol (high) - ...`; the S1 result is the same 479 genes |
| 5 | `Assistant` row | `Select model: ...`, the Model Catalog, pick `GPT-5.6 Terra`, `Select`; set its effort to `High` | The preset reads `Custom - phases below don't match a preset`; the next turn's usage names `gpt-5.6-terra (high)` |
| 6 | Model Catalog | Read | Columns `Model`, `Context`, `Input $/MTok`, `Output $/MTok`, `Cached $/MTok`, `Best For`; GPT-5.6 Luna `$0.20` input, `$1.20` output; tag `reads images and PDFs` on the three OpenAI models |
| 7 | Settings, `Advanced` | `Reset all local settings`, confirm | The page reloads with the default preset |

Measured with the debugger (every role on `openai:gpt-5.6-luna`, the default tier's `medium`): every turn's lead usage reports `reasoningEffort: medium`.

## A2 - A researcher's own provider key

Needs a deployment with personal keys on (`PROVIDER_KEY_ENCRYPTION_KEY` set). The dev environment has it off, so this flow is not measured. Expected: measure at UAT start.

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Settings, `Provider keys` on a deployment with the feature off | Read | `This deployment does not accept personal keys.` |
| 2 | Same, feature on | Read | `YOUR OWN PROVIDER KEYS` (CSS), the intro `A key you add pays for every model of its provider, ...`; rows `OpenAI`, `Anthropic`, `Google`, each `No key. The deployment's key is used, if it has one.` |
| 3 | `OpenAI key` | Paste `not-a-real-key-uat-0000000000`, `Save` | Button `Checking...`, then the sentence `OpenAI refused the key you added, so nothing ran on it. Replace or remove your OpenAI key in Settings, under Provider keys.`; nothing stored |
| 4 | `OpenAI key` | Paste a working key, `Save` | `...<last characters>, added <Mon D>.`; the quota pill turns into `Spend on your keys` with the own-key tooltip |
| 5 | New conversation | Send the S1 prompt | 479 genes; the usage is charged to the key (the tooltip's `On your keys this month: $<n>`) |
| 6 | `Remove OpenAI key` | Click | Back to `No key. The deployment's key is used, if it has one.` |
| 7 | A key whose account has no credit | Save it | Not stored: the provider's refusal is classified as no credit. A stored key that runs out later reads `...<hint>: This key has no credit. Add credit to the OpenAI account, or replace the key.` |

## A3 - The usage figures - core, once

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | After S1, under the composer | Read | `Conversation`, `<tokens> tokens`, `<cost>` joined by middle dots; tooltip `This conversation's total across all turns.` with rows `Assistant`, `Sub-agents`, `Total` |
| 2 | The trace header | Read | `<model> (<effort>) - <tokens>, <cost>`, tooltip `This turn` |
| 3 | Top bar quota pill | Hover | `$<used> / $<limit>`, `Account total this month, across all conversations.` and `<tokens> tokens`, `resets <Mon D>` joined by a middle dot |
| 4 | Compare | The quota pill grows by the conversation's total after the turn | Within a cent. The title and compaction calls are not charged (the backlog item "The title and the compactor are metered") |

Measured turn costs on `openai:gpt-5.6-luna`: a one-search build $0.074, a two-search build $0.05 to $0.14, an orthology edit $0.09 to $0.11, an off-topic reply $0.005.

## A4 - The data tab - once, on account A at the end

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Settings, `Data` | Read | Four actions: `Clear strategies`, `Clear site data`, `Clear ALL data`, `Clear ALL data + VEuPathDB`, each with its description. There is no export of all data (known limit) |
| 2 | `Clear site data` | Click, `Confirm` | The page reloads; gene sets, runs and control sets of this site are gone; conversations move to `Dismissed (<n>)`; memories stay |
| 3 | `Clear ALL data + VEuPathDB` | Click; type `delete my data`; `Confirm` | Toast `Data cleared` with `VEuPathDB strategies deleted: <n>. Memories deleted: <m>.`; reload after 4 s |

This is the sweep of `H1` in the [runner checklist](runner-checklist.md).

## A5 - Privacy - once

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Settings, `Privacy` | Read | `IMPROVING PATHFINDER` (CSS); the intro; checkbox `Let PathFinder learn from my strategies` |
| 2 | Checkbox | Untick, reload, reopen | Still unticked |

## A6 - Advanced - once

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Settings, `Advanced` | Untick `Show token usage` | The trace header loses its usage; the composer usage pill stays |
| 2 | Same | Tick `Show raw tool calls in the conversation` | Each trace row gains a `Raw` toggle showing `Parameters` and `Result` |
| 3 | Same | Tick `Also delete on VEuPathDB`, then delete a conversation from the sidebar | The dialog's own checkbox still decides; this toggle changes nothing today (record a minor if so) |

## A7 - Seeding - once, on a scratch account

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Settings, `Seeding` | `PlasmoDB` | Progress messages, then six seeded strategies in the sidebar and their control sets available to the assistant (`List control sets` in a later trace) |
| 2 | Cleanup | Settings, `Data`, `Clear site data`; delete the seeded conversations with the strategy box ticked | Nothing seeded remains |

Not measured (it writes six strategies to the account). Expected: measure at UAT start.
