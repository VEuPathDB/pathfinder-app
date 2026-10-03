---
type: Backlog
title: A card holds one change per stated part
description: A proposal card for a two-part message carries one change and calls the reading it prefers focused, although the comparison's unique genes show it is not.
tags: [lead, cards, proposals]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# A card holds one change per stated part

**What I did.** On tritrypdb, answered a text-term question with: use the phrase "GPI anchored", and also include the variant surface glycoprotein products.

**What I got.** `propose_changes` with one change (`text_expression: "GPI anchored"`) and the reply "I recommend the hyphen-free text search ... a focused direct-text result" for the 12-gene word reading, whose `compare_search_variants` `sample_unique_genes` hold TcIL3000_0_29570 (glucose-6-phosphate isomerase) and TcIL3000_10_11240 and _11250 (GPI mannosyltransferases).

**Why that's wrong.** The researcher asked for a union of two arms and was offered a replacement term; accepting builds a strategy they did not ask for, described as focused.

**Why it happens.** The card's changes are the Lead's own, and nothing holds them to the parts the message states; the comparison returns ids without products, so "focused" is never checked against the sample.

**Fix.** `propose_changes` is refused when a stated part of the message (the classifier's asks) has no change and no question on the card; `compare_search_variants` returns each unique gene with its product.

**What you'd get.** A card with two changes (the phrase arm and the VSG arm under UNION), and unique genes shown with products.
