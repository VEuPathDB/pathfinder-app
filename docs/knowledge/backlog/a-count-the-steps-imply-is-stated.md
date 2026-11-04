---
type: Backlog
title: A count the steps imply is stated
description: Asked how many genes a filter removed, the Lead usually points at the step counts beside the reply instead of giving the difference, although it holds both counts.
tags: [lead, reply, counts]
generated: { by: claude-code/opus-5.5, at: 2026-11-04T00:00:00Z }
status: proposed
---

# A count the steps imply is stated

## What I did

Ran the corpus case `uat-dry4-a-toxodb` on QA ToxoDB, on Luna, on one commit, five times
through the worker. The first message built Toxoplasma gondii GT1 genes with a signal
peptide and no ortholog in Neospora caninum Liverpool. The second message asked: "how many
of the signal-peptide genes did the ortholog filter remove?"

## What I got

The steps were Predicted Signal Peptide 680 genes, Orthology Phylogenetic Profile 1,240
genes, and their intersection 53 genes. `get_live_strategy_state` returned all three. One
reply said:

> The ortholog filter removed the signal-peptide genes that are not present in the final
> intersection. The exact removal count is shown by the step counts beside this reply

Another run of the same case said "The ortholog filter removed 627 of the signal-peptide
genes." Over the 13 stored runs of this case on three commits, 9 replies did not give 627.

## Why that's wrong

The researcher asked for one number and was told to subtract it from the facts. The facts
show 680 and 53, and they do not show 627. Nothing in the strategy is wrong, but the
question stays unanswered.

## Why it happens

`ai/lead/_lead_instructions.py` tells the Lead that the facts beside the reply show every
number, and the facts part (`domain/turn_facts.py`) has no field for a difference between
two step counts. The reply repeats that instruction. No run has tested this cause by
changing it.

## Fix

Not decided. The facts part can state what each combine step removed from each input, from
the counts the site reported, so the number comes from data and not from the model. Measure
the change with this case, repeated, before it ships.

## What you'd get

The same question answers "627" in every run: 680 signal-peptide genes and 53 in the
result, each number from the site.
