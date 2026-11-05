---
type: Backlog
title: A term the researcher already allowed is used
description: Told to use an obsolete GO term if it is the only one that fits, the assistant still ends the turn on a card that asks which term to use.
tags: [frame, cards, go-terms]
generated: { by: claude-code/opus-5.5, at: 2026-11-05T00:00:00Z }
status: proposed
---

# A term the researcher already allowed is used

## What I did

Ran the corpus case `uat-dry-b-fungidb` on QA FungiDB, on Luna, through the worker. The last
message asked for a GO cellular component term and said: "If the only fitting term is marked
obsolete, use it anyway and say so."

## What I got

Both reruns ended on a card and did not change the term. One reply said:

> the site marks it obsolete, so that status will be stated explicitly with the resulting
> count. Please choose the term to apply.

That run's result stayed at 44 genes, and the other's at 1,681. The case expects the term intersected with the ortholog
profile, 58 genes as measured on 2026-09-28.

## Why that's wrong

The researcher answered the question before it was asked and gets no new count. They must
repeat a decision they already stated.

## Why it happens

Not traced to one symbol. The reply names the term and asks anyway, so the choice the message
stated did not settle the pick. Trace the pick for this turn before any fix.

## Fix

Not decided. A value the researcher's message allows settles the pick with the fit it stated.

## What you'd get

The strategy on the obsolete anchored-component term, 58 genes, and a reply that says the term
is obsolete.
