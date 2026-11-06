---
type: Backlog
title: Gemini 4 Argon's price changes on 2026-12-01
description: Gemini 4 Argon is in the catalog at its introductory price of 2.00 / 0.10 / 10.00 per MTok. From 2026-12-01 Google charges 4.00 / 0.20 / 20.00; the price snapshot already meters the new price, but the catalog entry and /api/v1/models still show the old one until the entry is edited.
tags: [models, catalog, pricing]
generated: { by: claude-code/opus-5-5, at: 2026-11-06T00:00:00Z }
status: proposed
---

# Gemini 4 Argon's price changes on 2026-12-01

`google:gemini-4-argon` (`platform/model_catalog.py`) records Google's
introductory price, read on 2026-11-06: input 2.00, cached input 0.10 and
output 10.00 per MTok. Google's pricing page states that these rates apply
through 2026-11-30 and that from 2026-12-01 the model costs 4.00 / 0.20 /
20.00.

The entry has no `meter`, so `genai-prices` 0.2.1 meters its runs. That
release holds both prices with the change dated 2026-12-01, so the spend
meter and the quota rows charge the new price from that day without a code
change. The catalog's own `input_price`, `cached_input_price` and
`output_price` are what `GET /api/v1/models` returns and the Model Catalog
shows, and they stay at the introductory price until they are edited.

On or after 2026-12-01: read Google's pricing page again, set the entry to
the price it then states, bump `PRICES_AS_OF`, and change the Argon row of
`test_an_entry_records_the_price_its_provider_publishes` in
`tests/unit/platform/test_model_catalog.py`.
