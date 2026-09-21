---
type: Decision
title: A step count has one owner, and the wire is what the client reads
description: The commit reads every count back from VEuPathDB before it emits or persists, and the client stops letting a cached count mask the wire.
tags: [strategy-graph, transport, frontend]
generated: { by: claude-code/opus-5, at: 2026-09-21T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-21T00:00:00Z }
status: stable
---

# The bug this fixes

One edit produced three different sets of numbers in one turn: the reply and the
ledger read the strategy live, the graph snapshot of the same edit carried nulls
and pre-edit integers, and the rail carried a third set. A count had three
owners, so a reader could pick any of them and be wrong.

Each owner failed in its own way. The commit marked only the pushed steps
unknown, so every combine above a changed leaf kept the integer that described
the tree before the edit. The live read the Lead made went into its own answer
and nowhere else, so nothing the client received carried it. On the client, the
step lifecycle machine cached the count the canvas computed for itself and
preferred it over the wire for as long as the machine lived, so a zero it learnt
once could not be replaced by any later value.

# The decision

VEuPathDB owns a step's count. `replace_counts_with_wdks`
(`services/strategies/live_counts.py`) reads the strategy back and replaces
every local step's count with what the site answers; the commit calls it once,
after the push and before the graph snapshot and the persist, so the session,
the emitted snapshot, the stored strategy and the Lead's reply are one set of
numbers. `invalidate_counts_for` walks the graph's own parents, so a read that
fails leaves the changed step and every combine above it unknown instead of
stale. A build clears the counts as it replaces the tree, because a criterion id
can name a step in both trees.

The sync applies a step's filters and analyses before it reads the counts, so a
filtered step records the size it has with its filter on it.

On the client the wire is the authority: `resolveEstimatedSize` takes the count
the server sent whenever there is one, and the lifecycle machine's cache fills
in only for a step the wire does not count.
`POST /api/v1/conversations/{strategyId}/refresh-counts` runs the same read on
demand, behind the refresh control in the strategy rail. It is the researcher's
way out of a number they distrust, so it never confirms one: a site that answers
nothing is a 503 `SITE_UNAVAILABLE` and a strategy the site does not hold a 404
`STRATEGY_NOT_FOUND`, both of which leave the stored counts alone. The commit
path stays lenient, because there the invalidation has already marked the
changed branch unknown.

# What was rejected

- **A fourth cache.** Another store of counts, however fresh, would have added a
  fourth answer rather than settling which one is right.
- **Resetting the machine's cache whenever the strategy is rehydrated.** It
  leaves the cache authoritative between rehydrations, so the canvas's own
  computed count could mask the wire again the moment it ran.
- **Refreshing the counts only on the new route.** That makes a correct number
  something the researcher has to ask for.

# The residue

The canvas still computes provisional counts for its plan
(`POST /api/v1/conversations/step-counts`, `features/strategy/services/useStepCounts.ts`).
They now show only where the wire carries no count. They are measured against a
throwaway strategy, so they do not always agree with the one the site holds.

# Anchor

`services/strategies/live_counts.py`, `services/strategies/commit.py`,
`state/strategy/useStepSnapshot.ts`.
