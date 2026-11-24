---
type: Decision
title: An unreadable stored strategy opens for reading and refuses a build
description: A thread whose stored strategy does not parse or whose tree does not load still opens. The detail view shows the strategy as unreadable with the reason, and Explore runs and is told the same. A Build turn, a strategy write through the API and a durable job refuse with STRATEGY_AST_CORRUPT, so no write replaces the stored plan with an empty or partial graph. Rejected - locking the researcher out of the thread on every read, and loading the readable part of the tree.
tags: [strategy, persistence, explore, reliability]
generated: { by: claude-code/opus-5, at: 2026-11-24T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-11-24T00:00:00Z }
status: stable
---

# What was decided

A stored plan that does not parse (`parse_strategy_ast` returns `Unread`) or whose tree does
not load (`build_strategy_session` raises `StrategyAstCorruptError`) is read as unreadable,
never as "no tree":

- **Reads open.** `build_conversation_response` gives `strategyUnreadable` with the reason and
  no steps; the strategy panel and the compact view show "This strategy could not be read"
  with it. A turn's context is built with `thread_strategy_session`, an empty session whose
  `unreadable` names the reason, and Explore pins it (`pinned_unreadable_strategy`).
- **Writes refuse.** A Build turn stops at the Lead node with `STRATEGY_AST_CORRUPT`
  (`refuse_a_build_on_an_unreadable_plan`); the API's strategy writes and a durable job's
  context still build the session with `build_strategy_session`, which raises.

# Rejected

- **Refusing every read.** The researcher could no longer open the thread, see why, or ask
  Explore about it, and the failure text named only the conversation's id.
- **Loading the readable part.** A partial graph that a later write stores replaces the
  researcher's steps with the part that loaded.
