---
type: Backlog
title: An ambiguous request asks once with counts before it builds
description: Branch worktree-agent-a293400e9888ebfc7 holds the reviewed change that asks one question, with each reading's count, before BUILD when a request's readings give different results; it ships after a live run confirms it asks for ambiguous requests and stays quiet for clear ones.
tags: [lead, frame, consult, readings]
generated: { by: claude-code/opus-5.5, at: 2026-10-26T00:00:00Z }
status: proposed
---

# An ambiguous request asks once with counts before it builds

## What happens

The branch (commits 758cc3129, 03307fb02, eaa95dfe9 and eb7d290d2) asks once per request, before BUILD, with counted options, a union option for alternative searches, a coverage option for 'all of X', a remember offer for a picked definition, and a setting that uses the recommended reading. Two review rounds are closed; eb7d290d2 (typed words bound only by a reading other than the built one, a renamed criterion judged by the same rule, the records budget started at the send) has not had its scoped review. It was not merged because the QA sites were down and the change alters how the Lead and FRAME behave.

## Done when

A scoped review of eb7d290d2. Then a live run on QA: an 'all of a genus' request and a single-copy request each ask one card before any build, and the answer builds once with no repeated discovery; a concept with several definitions asks with a union option and offers to remember the pick; two clear requests ask nothing. Then merge the branch into main.

## Found after eb7d290d2

Review (not approved):
- A re-asked card where the researcher picks the built reading loops: `card_bindings.py` clears a pending entry only through `picked_runs()`, which leaves the built run out. Any click on the question must clear its entries.
- When the named criterion is gone, any criterion that differs from every run binds the pick, so a pass that drops the concept clears the gate (`pending_readings.py:75-77, 114`). Record the criterion ids present when asked and the record class; consider only new criteria of that class, else re-ask the stored card.

Live run on QA (2026-10-26, Luna, scratch mirror ask-once-live):
- FRAME measured four readings of "all Plasmodium species" (797, 1,088, 787, 395) but named none in its result, so the Lead's counted card was refused and a free-text question went out instead.
- A single-copy request across a clade and a kinase request asked nothing; FRAME recorded the text search as the only match although an InterPro domain search exists.
- Typed "InterPro protein kinase domain" bound IPR051334 (1 gene) instead of IPR000719, and the reply accepted the drop from 129 genes.
- The answer turn repeated the phyletic code lookup and one expression build.
- Clear requests asked nothing, as intended.

The live run is the gate: FRAME must report each reading it measured, with its run, before the card can work.
