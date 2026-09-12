---
type: Decision
title: A saved strategy is a criterion's input, resolved when the criterion binds
description: FRAME lists the user's saved strategies through a service and binds a criterion to one; the criterion carries the saved strategy's cloned steps, so the FRAME to BUILD conversion stays pure. Resolving the reference at build time, answering with a WDK strategy id, and dropping an input the listing cannot resolve were rejected.
tags: [decision, agents, frame, saved-strategies, wdk]
generated: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
status: stable
---

# What was decided

A researcher saves a strategy so other work can start from it. Until now no
agent could see that library, so a request that started from a saved strategy
ended with the agent asking for a WDK strategy id, and then building the one
criterion it could bind on its own.

**The library is a service read, and FRAME has a tool for it.**
`services/strategies/saved_library.py::list_saved_strategies` returns the
caller's saved threads on the current site (name, thread id, WDK id, record
type, root count, step count), through
`ConversationRepository.list_saved_strategies`, which drives from
`conversations` and inherits its `(user_id, application_id)` predicates
([the thread owns the strategy](conversation-thread-and-strategy-split.md)).
The FRAME tool `list_saved_strategies` calls that service; it never touches the
repository.

**A criterion binds to a saved strategy instead of to a search.**
`set_criterion(saved_strategy=...)` takes a name, a WDK id or a thread id from
that listing and records a `Criterion` with a `SavedStrategyRef` and an empty
`search_name`. `Criterion.bound` is true for either, so `ready_to_build`,
the workspace and the ledger all read one criterion shape.

**The reference resolves when it binds, not when it builds.** The ref carries
the saved strategy's steps, read from WDK and cloned with fresh ids by
`clone_saved_strategy`, the same function the panel's "Insert saved here" runs.
`build_step_tree` then splices that subtree in with no I/O of its own.

**The saved subtree lands on the secondary input.** WDK marks the SECONDARY
input of a combine as the collapsed saved strategy
(`veupathdb-mcp: src/veupathdb_mcp/wdk/strategy_snapshot.py` reads it back the same
way), so
the conversion moves a saved operand there and mirrors the operator that is not
symmetric: MINUS becomes RMINUS, LONLY becomes RONLY. The combine carries
`expanded_strategy_id` and `expanded_name`, which is what renders it collapsed.

**An unresolved input stops the build mechanically.** A reference the listing
does not hold records the criterion with an open `saved_strategy` slot BEFORE
the `ModelRetry` that names the listing, so `ready_to_build` is false whatever
the model does next, and `drop_criterion` refuses that criterion by name. The
frame ends `needs_user` with the listing's names in the question.

**The two UI entry points reuse the one route.** `POST
/conversations/{id}/insert-saved` accepts an empty `targetStepId`: with no step
to combine with, the cloned saved strategy becomes the thread's root. The empty
Strategy panel opens the same picker the step kebab opens, and the Saved
strategies page's "Use in new chat" begins a thread and inserts through that
route before navigating to it.

# What was rejected

**Resolving the reference at build time.** The criterion would carry only the
id, and the materialization would read WDK. It was rejected because the one
call site that turns a spec into steps is the Lead's `build_strategy`, and the
conversion under it (`build_step_tree`) is the pure FRAME to BUILD seam: a WDK
read there makes the seam async, makes every caller of it async, and makes
`ready_to_build` a promise rather than a statement. Binding time is also where
the user is still in the loop, so a saved strategy that cannot be read is a
question the same turn can ask.

**Answering with a WDK strategy id.** This is what the measured run did: the
frame asked for the id, the user gave `330534203`, and nothing could consume
it. An id is not a reference the agent can check ownership on; the listing is,
because it is scoped to the caller. The id still resolves, but only when the
listing holds it.

**Dropping the criterion the listing cannot resolve.** That is the defect, not
a fallback: the measured turn dropped the saved input, built
`GenesWithSignalPeptide` alone, reported 603 genes, and left that strategy
active on the thread.

**A second route for the root insert.** A `POST .../insert-saved-as-root` would
duplicate the clone, the push and the consumer record. The existing route
already knows the thread has no steps.

# What would falsify this

`.../tests/unit/domain/strategy/test_operational_spec_saved.py`
fails if a saved criterion stops counting as bound, if the saved subtree stops
landing on the secondary input with the operator mirrored, or if an open saved
slot stops blocking the build.
`.../tests/unit/ai/tools/test_frame_saved.py` fails if the FRAME toolset
loses the lookup, if an unknown reference stops naming the listing, or if the
open criterion becomes droppable.
`.../tests/integration/services/test_saved_strategy_library.py` fails if the
listing returns another user's rows, another site's rows, or an unsaved thread.
