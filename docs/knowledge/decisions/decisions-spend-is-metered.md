---
type: Decision
title: Decisions spend is metered as gpt-6-luna input
description: Every Decisions call is sent on the key that pays for OpenAI in the turn, except the turn's router, which runs on the deployment's key, and is charged to the turn as spend outside the Lead, priced as gpt-6-luna input with no output charge; an unmetered transport and a separate price table were rejected.
tags: [metering, decisions, provider-keys, cost]
generated: { by: claude-code/opus-5.5, at: 2026-11-02T00:00:00Z }
status: stable
---

# What was decided

`ai/capabilities/decisions_spend.py::install_decisions_transport` installs, in the api and
the worker, the transport `veupathdb_mcp.catalog.decide` sends through. A live deployment
posts each request with the OpenAI provider `platform/model_keys.py::keyed_provider`
returns for gpt-6-luna: the researcher's live key when one is attached to the turn, else
the deployment's. The turn's router is the one exception: it is sent inside
`decisions_on_the_deployment()` on `platform/model_keys.py::deployment_provider`, charged as
paid by the deployment, and asked only while the researcher's monthly deployment allowance
holds ([a thread answers in Explore or Build](a-thread-answers-in-explore-or-build.md)). A
mock deployment asks no decision.

Each answer's usage (input tokens, cache reads, cache writes) is priced by
`assistant_core.cost.cost_for_run` as gpt-6-luna with no output tokens, and reported to the
sink `decisions_spend_to` holds. `lead_node` holds a sink that adds the spend to the turn's
capture as spend outside the Lead, so the turn's usage rows charge it once, to the payer.
A call outside a turn is sent and charged to no one.

A refused or unanswered request raises an error that names the status and carries no
provider body, so a key never reaches a log; `decide` answers None and its caller keeps
its own fallback.

# Why

OpenAI prices Decisions on gpt-6-luna as uncached input at $0.10 per million tokens, with
gpt-6-luna's cache read and write rates and no charge for output. The catalog already
holds those rates, so the price needs no table of its own. The catalog's own Decisions
calls (search candidates, narrowed parameter reads) and the message reading spend on the
same key and reach the same rows.

# Rejected

**The library's own transport.** It posts on the deployment's key from the environment,
so a researcher's key would never pay and the spend would reach no row.

**A Decisions price table.** It would restate the catalog's gpt-6-luna rates and drift
from them.
