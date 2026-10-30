---
type: Decision
title: A reply states what the turn wrote
description: What the turn wrote to the strategy is a fact the facts part renders from the turn's write markers and the live tree, never a claim the Lead makes; the strategy_changed flag and its misreported-change rule, matching the prose for change verbs, and a UI-only "strategy unchanged" card were rejected.
tags: [agents, lead, honesty, facts]
generated: { by: claude-code/opus-5, at: 2026-09-14T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-10-30T00:00:00Z }
status: stable
---

# What was decided

The facts part beside the reply states what the turn wrote
([the product renders the facts](the-product-renders-the-facts-the-reply-narrates.md)): the
steps the strategy holds now with their counts, each step this turn's writes moved with its
count before the edit, the root count before and after, the titles of the steps the turn
deleted, and the strategy's last change (`TurnFacts.last_change`). The turn's markers are the
record: `TurnMarkers.built`, `TurnMarkers.edited`, together `changed_strategy`. Every path that
writes the strategy sets a marker: a build and a resync through `PipelineState.record_build`,
a clear through `edited`. A recovery pass records a build only when the strategy's revision
hash or its pushed WDK ids moved, so a pass that repaired nothing marks nothing.

`LeadResponse` carries no flag for the change. The Lead's note says what the change means, and
the facts part says what it was.

# Why

A reply that claims a change the turn never made, or hides one it did, misleads only while
the reader has no other account of the turn. The facts part is that account, written from the
same markers and the same tree the strategy holds, so the change is shown whatever the note
says.

# What was rejected

- **A required `strategy_changed` flag and a rule that refuses an answer whose flag disagrees
  with the markers.** The flag was the model's own report of the change, not the sentence the
  researcher reads, so the check refused a self-report while the prose stayed unread, and every
  answer the rule let through was set to the record's value anyway.
- **Matching the prose for change verbs.** A list of verbs ("removed", "replaced", "added")
  fits the one measured reply and misses the next phrasing, and it fires on a reply that
  describes a change the user asked for without claiming it happened.
- **A "strategy unchanged" card in the thread.** A card that only denies a claim adds a second
  account beside the facts part; the facts part already shows the strategy as it is.
