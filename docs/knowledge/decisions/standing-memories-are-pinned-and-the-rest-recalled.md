---
type: Decision
title: Standing memories are pinned and the rest are recalled
description: A fresh turn pins only the researcher's preferences and gives the Lead a count of every other kind; the Lead recalls those with search_memory. Ranking the top memories of every kind into every turn was rejected.
tags: [memory, lead, context]
generated: { by: claude-code/opus-5, at: 2026-10-04T00:00:00Z }
status: stable
---

# What was decided

A fresh turn reads only the standing kinds, the researcher's preferences, into the
Lead's and every sub-agent's instructions (`ai/graph/_lead_turn._turn_scope`). Every
other kind (strategies, cases, gene set memories, knowledge) is counted per site
(`memory_index`, `StrategyDomainState.memory_index`) and named in the Lead's
briefing as "What you can recall about this user"; the Lead recalls one with
`search_memory`, which it may call before the turn is classified, and FRAME keeps
its own case search before it binds. A "Recalled memories" card shows a memory the
first time the conversation recalls it (`StrategyDomainState.memories_to_show`).

# Why

A preference is an instruction the researcher gave; the model cannot know to look
for one it does not know exists, so it is pinned on every turn. A strategy, a case
or a note from another conversation answers some requests and not others. Ranking
the top eight by similarity into every turn put other conversations' strategies
into every request, where an old strategy can steer a new question, and the
pinned block held one or two of the ten cases FRAME's own search returns.

# What was rejected

- **The top memories of every kind on every turn.** It is what the turn did: the
  ranking runs on the message alone, so a follow-up such as "now drop the
  expression step" recalls by its words, not by what it needs.
- **Recall by the model alone, with no index.** A model that does not know a
  memory exists has no reason to search; the count per kind costs one listing per
  kind and names what is there without reading it into the turn.
