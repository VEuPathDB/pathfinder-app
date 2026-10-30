---
type: Backlog
title: A computed step added later carries the snapshot note
description: Every WDK strategy create sends the graph's description, which carries the snapshot note once a saved computed comparison is bound, but veupathdb-py's update_strategy sends only a step tree and a name, so a strategy the site already holds keeps its old description; release a client that sends the description on update, with a matching veupathdb-mcp release, and send it on every update.
tags: [orthomcl, strategy, wdk, veupathdb-py]
generated: { by: claude-code/opus-5.5, at: 2026-10-25T00:00:00Z }
status: proposed
---

# A computed step added later carries the snapshot note

## What happens

A build or an edit whose spec binds a saved computed comparison writes
`noted_description(...)` to the graph's `description`, and `sync_strategy_for_site` sends
that description on every create.
A strategy the site already holds is changed with `StrategyAPI.update_strategy`, which
sends a step tree and a name and no description. An edit that adds a computed step to such
a strategy writes the note to the graph and not to the site, so a researcher who opens the
strategy on the site does not read that the group ids are fixed and the count can change.

## Change

In veupathdb-py, let `update_strategy` send `description` in its
`PATCH /users/{id}/strategies/{id}` body (WDK's strategy PATCH takes it beside `name`;
confirm against `StrategyService` first) and release it. veupathdb-mcp declares its own
source for veupathdb-py, so the same client tag needs a veupathdb-mcp release that pins it,
or the resolution fails on conflicting URLs. Take both releases here, and send the graph's
description from `sync._create_or_update_wdk_strategy` when it updates a strategy whose
description WDK does not hold.

## Done when

A unit test edits a computed criterion into a strategy that holds a WDK id and asserts that
the update sends the graph's description, `SNAPSHOT_NOTE` included.
