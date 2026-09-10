---
type: Decision
title: A resource is owned by a user under one application
description: Every owned table carries application_id, the scope key is (user_id, application_id) inside the existing ownership helpers, memories are namespaced under the application, and the monthly cap stays per user with per-application attribution; per-application user rows and one database per application were rejected.
tags: [tenancy, security, authz, memory, quota, persistence]
generated: { by: claude-code/opus-5, at: 2026-08-19T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-19T00:00:00Z }
status: stable
---

# What was decided

One person can drive several assistants. The user is the same person on all of
them, and the work is not the same work.

**The scope key is `(user_id, application_id)`.** The application comes from
`application_id_ctx` (`assistant_core/platform/context.py`), which the request resolver sets
from the service token and a worker job sets from the conversation row. A
periodic job and the chat debugger read neither, so they name this deployment
themselves (`jobs/auth_context.py::attach_application`); the runtime's own
default names no product. Six
tables carry the column, `NOT NULL DEFAULT 'pathfinder'`: `conversations`,
`gene_sets`, `control_sets`, `experiments`, `memory_tombstones`,
`monthly_usage`. Messages, conversation events, background tasks, task
progress and scratchpad notes hang off a conversation and are scoped through
it.

**A resource of the same user under another application is a stranger's
resource.** The check lives inside the helpers that already decide ownership
(`assistant_core.conversation.authz.owned_by_caller`, the gene-set, experiment
and control-set stores, the repository list queries), so no route grew a
parallel check and every route inherits the rule. The refusal is whatever that
route already gives a non-owner: 404 where existence is hidden, 403 where the
helper raises it.

**Memories move under the application.** The namespace is
`("app", <application>, "user", <user>, <kind>)`, built in one function
(`assistant_core/memory/store.py::memory_namespace`), so a memory written by one assistant
is invisible to another and a tombstone blocks re-writing only in the
application that wrote it.

**The monthly cap stays per user; attribution is per application.**
`accumulate` writes the row of the calling application, and `get_current` sums
every application of that user for the period. A user cannot double their
budget by using a second assistant, and the operator can still read what each
assistant cost.

# What was rejected

**One user row per application.** It makes the scope key a single column and
needs no join, and it breaks the one thing that must not break: the internal
user is the VEuPathDB identity (`users.external_id` is the email), so splitting
it would give one researcher several PathFinder users, several WDK guest
tokens, and no way to hold one budget.

**One database per application.** Perfect isolation, and it costs a database,
a migration run, a connection pool and a backup per assistant, with no shared
quota and no cross-application answer to "what does this user cost". Row-level
scoping in shared tables gives the same isolation for the resources that have
an owner.

**Widening the wire.** Responses do not carry `applicationId`. Tenancy is a
server-side scope, and a caller already knows its application: it is the one
the service token it presents declares. No endpoint reports the resolved
principal.

# What this does not do

**A purge destroys only what its caller can see.** `DELETE /api/v1/user/data`
dismisses or deletes the conversations, gene sets, experiments and control sets
of the calling application, and leaves the same user's data under every other
application untouched, because a caller that cannot read a resource must not be
able to destroy it. `deleteWdk=true` deletes on VEuPathDB only the strategies
those conversations built (each thread's `wdk_strategy_id`, which now lives on
its strategy attachment, see
[the thread/strategy split](conversation-thread-and-strategy-split.md)),
never a saved strategy a chat
merely imported: nothing records whether such a strategy came from PathFinder
or from the user's own work on the website, and another conversation may still
consume it. A person who wants everything erased across every assistant
needs a first-party action that names no application; that action does not
exist yet, and adding it is not the same decision as this one.

There is no applications table, so an application id is whatever
`PATHFINDER_SERVICE_TOKENS` declares, and revoking one is deleting its token.
There is no per-application budget: the cap is the user's. Both are named in
the platform assessment as separate work.
