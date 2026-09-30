---
type: Backlog
title: Each corpus case runs as a fresh user
description: Every corpus case runs as the chat debugger's one fixed PathFinder user, so gene sets, memories and cases from earlier runs are read by later ones; a user id per case, carried through the debugger, and its memories dropped at the end would isolate them.
tags: [evals, devtools, memory]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# Each corpus case runs as a fresh user

**What I did.** Ran the corpus three times on the round-3 images.

**What I got.** `uat-dry-c-plasmodb` turn 12: `list_gene_sets` returned 275 sets on the
test user, one of them an earlier run's "vaccine candidates draft" of 39 genes, and the
reply "An earlier gene set with the same name contains 39 genes" passed the case's
`replyMentions` "39". `an-assent-to-build-builds` turn 1 retrieved a preference memory
and a case written by `uat-dry-c-plasmodb`.

**Why that's wrong.** A case's result depends on which cases ran before it on the same
database, so an expectation can pass on another run's state and fail on a clean one.

**Why it happens.** `devtools/chat.py` runs every turn as `DEV_USER_ID`: the in-process
turn (`attach_user_id`, `TurnRequest.user_id`), the worker job and the two user rows the
debugger creates. `devtools/eval_runner.py` cannot choose the user without that seam.

**Fix.** Add `user_id` to `RunArgs` (default `DEV_USER_ID`), read it at the six places
`chat.py` names the constant, give `run_one_case` a `uuid4()` user per case, and delete
that user's memory namespaces (`("user", user_id, kind)` for the five kinds) when the
case ends. The WDK account stays shared: its strategies are named per conversation.

**What you'd get.** A case reads only what its own turns wrote; the dry-c "39" passes
only when turn 9 of the same case saved the set.
