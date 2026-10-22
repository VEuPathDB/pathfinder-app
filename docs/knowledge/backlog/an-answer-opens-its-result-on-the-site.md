---
type: Backlog
title: An answer opens its result on the site
description: The link to the strategy on the VEuPathDB site sits only in the right rail's Strategy panel and the canvas top bar; the answer that reports a result carries none, so going from the answer to the site's strategy and its record list takes a search through the interface.
tags: [frontend, strategy, site-link, orthomcl]
generated: { by: claude-code/opus-5, at: 2026-10-21T00:00:00Z }
status: proposed
---

# An answer opens its result on the site

## What happens

`strategy.wdkUrl` is rendered in `features/conversation/rail/StrategyPanel.tsx` and
`features/strategy/graph/components/CanvasTopbar.tsx`. The assistant message that
reports a count (for example a list of ortholog groups) carries no link, so a
researcher who wants the result on OrthoMCL, with its record list, its columns and its
download, has to find the rail panel or open the canvas first.

## Change

1. The answer part that reports a step's result carries "Open on <site>", which opens
   that step's records in the site's strategy workspace (the strategy and step ids
   form the site's step URL, as `features/sidebar/wdkStrategyRef.ts` already parses).
2. The rail link names what it opens ("Open strategy on OrthoMCL").

## Measure first

Which step URL the site opens on its result list for each record type (gene,
ortholog group, protein), on QA, before writing the link.

## Done when

An answer that reports a result opens that result's record list on the site in one
click, for a gene search and an OrthoMCL group search, with a component test for the
link.
