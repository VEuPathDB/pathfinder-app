---
type: Decision
title: A researcher can turn memory off
description: A switch on the Memory tab, stored on the account as users.memory_enabled, gives every turn, durable task and audit turn of that researcher no memory store, so nothing is recalled or written; an account that never set it follows MEMORY_ON_BY_DEFAULT, off unless the deployment sets it; a flag on each request and hiding the memory tools were rejected.
tags: [memory, settings, testing]
generated: { by: claude-code/opus-5, at: 2026-11-07T00:00:00Z }
status: stable
---

# What was decided

The Memory tab shows "Use memory in my conversations" (`MemorySwitch.tsx`), read and written
through `GET` and `PUT /api/v1/me/memory` and stored as `users.memory_enabled`. The column is
empty until the researcher sets the switch, and an empty one follows the deployment's
`MEMORY_ON_BY_DEFAULT` (`services/memory_setting.py::memory_is_on`), which is off when unset.
The dev and QA deployments leave it unset; production sets it on. Migration `2026_11_09_0001`
emptied every account's stored choice, so each account follows the deployment until its
researcher sets the switch again.
Every context a turn runs in asks `services/memory_setting.py::the_researchers_store` for its
memory store: the PathFinder turn (`assistants/pathfinder_spec.py`), the durable task
(`jobs/runtime.py`) and the audit turn (`ai/audit/turn.py`). With the switch off the context
holds no store. Every memory reader and writer already treats a missing store as no memory:
the pinned preferences and the memory index read nothing, `search_memory` recalls nothing,
`remember` answers that memory is unavailable, and `finalize_turn` writes no auto-memory. The
stored memories stay, and turning the switch on reads them again.

# Why

A run that is to be repeated, the same question on the same or another model, has to start
from the same state. A recalled case or a pinned preference from an earlier conversation can
steer the next answer, so a wrong answer cannot be told apart from a memory that caused it.

The account holds the switch because the researcher turns it once and every device and every
tab follows it, durable tasks included, which no request body reaches.

The default lives on the deployment, not on the column, because the stage decides it: dev and
QA keep runs repeatable while production serves researchers who expect to be remembered, and
one image runs on every stage.

# What was rejected

- **A flag on each chat request.** A durable task and the completion turn it opens carry no
  request body, so they would read memory while the turn that started them did not.
- **Hiding `search_memory` and `remember` from the agents.** Five toolsets register them, and
  a missing store already makes both answer with nothing; hiding them adds a prepare to each
  registration and changes nothing a turn can do.
