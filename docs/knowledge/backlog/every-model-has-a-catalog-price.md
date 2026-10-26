---
type: Backlog
title: Every model has a catalog price
description: OpenAI and Google models have no price meter in the model catalog, so their cost comes from the bundled genai_prices snapshot; give each deployment model a meter with its provider's listed rates, including cache-write rates and long-context tiers.
tags: [billing, models]
generated: { by: claude-code/opus-5.5, at: 2026-10-26T00:00:00Z }
status: proposed
---

# Every model has a catalog price

## What happens

The snapshot matches OpenAI's listed Luna rates today, including the cache-write rate of 1.25x input, so costs are correct; the dependence on a third-party snapshot is the risk.

## Done when

A test fails if a selectable model has no catalog meter; each meter's rates cite the provider's pricing page.
