---
type: Backlog
title: A computed step added later carries the snapshot note
description: A strategy created by a build on a saved computed comparison carries the snapshot note as its WDK description, but veupathdb-py's update_strategy sends only a step tree and a name, so a computed step added to a strategy the site already holds leaves the site's description empty; release a client that sends the description on update and send it from the edit path.
tags: [orthomcl, strategy, wdk, veupathdb-py]
generated: { by: claude-code/opus-5.5, at: 2026-10-25T00:00:00Z }
status: proposed
---

# A computed step added later carries the snapshot note

## What happens

`build_the_minted` writes `snapshot_note(...)` into the build's context, and
`sync_strategy_for_site` sends it as the `description` of the strategy it creates
(`StrategyAPI.create_strategy`). A strategy the site already holds is updated with
`StrategyAPI.update_strategy`, which sends a step tree and a name and no description. An
edit that adds a computed comparison's step to that strategy, or a later build under the
same WDK strategy, leaves the site's description as it was, so a researcher who opens the
strategy on the site does not read that the group ids are fixed and the count can change.

## Change

In veupathdb-py, let `update_strategy` send `description` in its
`PATCH /users/{id}/strategies/{id}` body (WDK's strategy PATCH takes it beside `name`;
confirm against `StrategyService` first), release it, take the release here, and send
`SNAPSHOT_NOTE` from the edit path when its spec binds a saved comparison.

## Done when

A unit test edits a computed criterion into a strategy that holds a WDK id and asserts that
the update sends `SNAPSHOT_NOTE` as the description.
