---
type: Backlog
title: A genus the message names is stated on its species
description: An organism the message names at genus level binds as its species entries marked chosen, a refused bind leaves a stale took 0 of 0 row, and the classifier later withdraws the genus as assumed.
tags: [facts, organism, bound-values]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# A genus the message names is stated on its species

**What I did.** On the portal, "Genes across Cryptosporidium with the GO term 'protein glycosylation'", then narrowed to Cryptosporidium parvum Iowa II.

**What I got.** Organism: all 30 Cryptosporidium entries "(chosen)" with the row "Organism took 0 of the 0 entries that match 'Cryptosporidium'" from the refused `set_criterion` (organism "Cryptosporidium" is no vocabulary entry); the row stays after the edit. On the edit turn `classify_user_intent` records the withdrawn "Cryptosporidium" with `source: assumed`, though the message stated it.

**Why that's wrong.** Thirty chosen rows for one stated word, a measurement row from a call that bound nothing, and a stated requirement recorded as assumed.

**Why it happens.** `sourced` matches a value's label against the message; the genus is a tree parent whose leaves were bound, and no leaf label is in the message. The lookup row is recorded on the refused call and never dropped. The classifier reads the withdrawn organism's source from the request it withdraws, not from the message that stated it.

**Fix.** A bound value whose tree parent the message names is stated, shown as the parent with its leaf count; a lookup row is recorded only on a bind that completes; a withdrawn constraint keeps the source the thread recorded for it.

**What you'd get.** `Organism: Cryptosporidium (30 organisms) (stated)`, no took-0-of-0 row, and the withdrawn genus recorded as stated.
