---
type: Backlog
title: The write-through store and the task spawner are generic machinery held in the app
description: platform/store.py is a 158-line cache plus retrying upsert over an Identifiable protocol with one app import, the spawn helper in platform/tasks.py, and both are persistence mechanism any assistant deployment needs.
tags: [platform, persistence, assistant-core, wrong-repo]
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
status: stable
---

# What I did

Read `apps/api/src/pathfinder/platform/store.py` and
`apps/api/src/pathfinder/platform/tasks.py`, and listed what imports each.

# What I got

`store.py` is 158 lines: an `Identifiable` protocol with a string `id`, and
`WriteThruStore[T: Identifiable]`, an in-memory cache whose subclasses supply an
ORM model and two row converters, with a tenacity retry around the upsert and
the delete. It names one app symbol, line 31, `from pathfinder.platform.tasks
import spawn`. Everything else comes from `assistant_core.platform.db`,
`assistant_core.platform.logging`, SQLAlchemy and tenacity.

`tasks.py` is 37 lines around `asyncio.create_task` with a module-level set that
keeps a strong reference until the task finishes. It names nothing of
PathFinder's either.

Two stores subclass the base: `services/gene_sets/store.py:23` and
`services/experiment/store.py:10`.

# Why that's wrong

Both files are mechanism with no product in them, so any deployment built on
this runtime writes them again: the reference-retention rule for fire-and-forget
tasks in particular is the kind of thing that is rediscovered by losing a write.
They also sit in the app's `platform/`, which reads as the place for what this
deployment is, next to the settings and the identity strings.

# Why it happens

Both were written for the first two stores that needed them and never moved
when the runtime became a package.

# Fix

Library first, in `ai-assistant-platform`: move both into
`assistant_core/platform/`, `store.py` beside `db.py` and the spawn helper
beside it, with their tests. Then here: delete both files, point
`services/gene_sets/store.py` and `services/experiment/store.py` at the
runtime's base class, update the one test fixture that patches the spawn symbol
by name, and take them at the library's next tag. Drop `store` and `tasks` from
the `platform/` line of the backend directory in `CLAUDE.md` in the same change.

# What you'd get

One write-through store and one task spawner for every deployment, tested in
the package that owns the session factory, and an app `platform/` that holds
only what this deployment is.
