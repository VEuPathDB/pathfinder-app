---
type: Decision
title: Our own admission record reads incomplete, because one account cannot prove isolation
description: The served endpoint is admitted by a live-marked run of veupathdb-mcp-conformance against it, carrying the registered VEuPathDB account as the first credential and the service token as the second. Making the service token the owning identity would settle the isolation pair, and was rejected because it turns the twenty-nine substantive checks into calls a service credential is refused.
tags: [mcp, conformance, admission, testing, credentials]
generated: { by: claude-code/opus-5, at: 2026-08-25T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-25T00:00:00Z }
status: stable
---

# What was decided

`apps/api/src/pathfinder/tests/integration/mcp/test_conformance_ours.py` composes
the suite as its own pytest process against the served endpoint, and reads the
admission record the run writes. It is marked `live_wdk`, so it runs in the
nightly lane and never blocks a pull request.

**The first credential is the registered VEuPathDB account.** Sixteen of the
seventeen tools carry sample arguments in that run, so family 3 calls real reads
twice and family 4 probes every read-only tool with an argument its own schema
refuses. The account-state hook lists the account's WDK strategies, which is
what a read must leave alone and what the one non-destructive write creates and
takes away again. The suite runs the hook on an event loop of its own, so the
hook opens and closes a WDK client of its own: a pooled connection belongs to
the loop that opened it, and the per-site client this process caches belongs to
the loop that built the step. The comparison is over the whole account, so the
run needs that account to itself: a second client writing to it reports a change
no served call made.

**The second credential is the service token**, which family 2 holds to the same
leak rule as the first: neither secret may appear in any result or error the
server produces.

**No isolation tool is named**, because naming one requires a resource the
second identity owns and the service credential owns nothing in WDK. The two
isolation checks therefore skip, and so does the idempotency comparison, which
compares a repeated read and finds that no served tool declares
`idempotentHint`.

**The slow tool is `search_example_plans`**, driven past a one second budget.
It was unnamed while an abandoned call outlived its caller and three of them
killed the container inside its 2g ceiling; the pass now embeds a batch at a
time, refuses once the caller has disconnected, and holds its site's lock, so
three abandoned calls leave the server serving
([per-site catalogs are evicted under a budget](per-site-catalogs-are-evicted-and-the-warm-up-does-not-block-the-bind.md)).
Family 5 settles all four of its checks.

Three skips out of thirty-two checks leave the verdict `incomplete`.

# What was rejected

**Making the service token the first credential and the VEuPathDB account the
second.** It settles the isolation pair exactly - the account reads its own step
and the service credential is refused it - and it was rejected because every
other check then runs as a credential that WDK refuses every step read to. The
account comparison would compare an account nothing touched, the non-destructive
write would never write, and family 4 would probe tools that fail before their
own validation runs. A record that reads `pass` because its checks stopped
reaching the server is worse than one that reads `incomplete` and says which
three checks did not run.

**Provisioning a second registered VEuPathDB account.** Not ours to make; it is
the owner's call, recorded as decision point 7 of the execution plan. When one
exists, `--mcp-bearer-second` carries it and `--mcp-isolation-tool` names
`get_step_estimated_size` over a step that account owns; the two skips become
passes and the constant that names them shrinks.

# What this costs

The service-credential refusal is still proven, one layer down:
`test_served_wdk_mcp.py::test_an_application_credential_cannot_read_a_step` and
`::test_a_user_token_is_refused_the_step_of_another_user` run in the same lane.
What the admission record cannot say is that a *foreign server* refuses one
user's resource to another, and that is the sentence a second account buys.
