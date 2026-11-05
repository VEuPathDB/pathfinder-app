---
type: Backlog
title: A count before an edit is read from the facts
description: Asked what the count was before a deletion, the Lead says the count was not retained, while the facts beside the same reply show it.
tags: [lead, reply, counts]
generated: { by: claude-code/opus-5.5, at: 2026-11-05T00:00:00Z }
status: proposed
---

# A count before an edit is read from the facts

## What I did

Ran the corpus case `uat-dry-d-amoebadb` on QA AmoebaDB, on Luna, through the worker. The
third message deleted the signal peptide step. The fourth asked: "What was the count right
before you deleted the signal peptide step, and what is it after?"

## What I got

The facts beside the reply said:

> Last change: deleted Predicted Signal Peptide; 22 genes before, 74 genes after

The reply said:

> The pre-deletion result count was not retained in the readable strategy ledger, so I cannot
> verify that earlier count

## Why that's wrong

The reply and the facts disagree on the same screen. The researcher is told a number is lost
when the page shows it.

## Why it happens

The turn called `get_live_strategy_state` and `read_ledger_section`. The first returned 74 and
not 22, and the second returned neither, so nothing the Lead read held the count before the
deletion.

## Fix

Not decided. The Lead reads the count before the last edit from the same record that the facts
part reads.

## What you'd get

"22 genes before the deletion and 74 after."
