---
type: Backlog
title: Thread surgery is a runtime primitive
description: Fork and revert are copy code in PathFinder that must track rules owned by assistant-core, LangGraph and WDK; move fork into the runtime as fork_thread, make revert a fork without the tail, and give external effects a compensating saga.
tags: [fork, revert, assistant-core, architecture]
generated: { by: claude-code/opus-5.5, at: 2026-10-26T00:00:00Z }
status: proposed
---

# Thread surgery is a runtime primitive

## What happens

The safety fixes (thread lock, liveness refusals, scoped message upsert, compensation, checkpoint schema contract, blob pruning) shipped. The structural cause remains: every new column, field or rule in another layer has to be mirrored by hand. Design points: an explicit copy policy per column with a test that fails on an unclassified column; one id map; history rebuilt from the copied log instead of copied checkpoint blobs; cuts on cursors, never timestamps; no cascading keys from a branch to its parent; external side effects owned and undone on failure.

## Done when

A written design is approved before any code; then fork_thread in assistant-core with a PathFinder hook, and revert implemented as fork without the tail.
