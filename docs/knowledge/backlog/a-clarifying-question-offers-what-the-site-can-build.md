---
type: Backlog
title: A clarifying question offers what the site can build
description: When a request is underspecified, the turn asks the user for raw parameters ("what fixed copy-number thresholds?") and then still refuses; a clarifying question instead proposes two or three concrete readings the site can build, each with what it would return and its trade-off, in the user's own terms.
tags: [lead, frame, consult, ux, orthomcl]
generated: { by: claude-code/opus-5, at: 2026-10-21T00:00:00Z }
status: proposed
---

# A clarifying question offers what the site can build

## What happens

On difficult OrthoMCL requests the clarifying question asks for search parameters in the
abstract ("What fixed copy-number thresholds should define an expanded orthogroup, for
example at least how many Toxoplasma genes per orthogroup and fewer than how many
Plasmodium genes?"). An answer in biology terms is followed by the same refusal ("the exact
comparison remains unavailable"), and the exchange ends without a strategy, although the
site can approximate the request (card 50).

## Change

1. A consult that the Lead or FRAME raises offers two or three readings it can build,
   each one line: what it means biologically, what the strategy does, roughly what it
   returns or what it misses; the user picks one or answers freely.
2. The readings come from what the catalog can express (the phyletic grammar, transforms,
   counts, the per-step count of card 47), so a reading offered is a reading the turn
   can build.
3. An answer in the user's terms (for example "2-5 copies, at least 2x more") is mapped to
   the closest buildable reading, stated back in one sentence, and built; the turn does
   not ask again for the same thing in parameter terms.
4. A request that no reading can approximate says so once, with the reason and the
   nearest thing it can build.
5. A Lead question that rewords a recorded one without its requirement key shows beside it.

## Related

Card 45 (an "all" over many genomes is asked about) and card 50 (a copy-number
comparison between clades is built in bands) are two cases of this rule.

## Done when

The copy-number question and the "all Plasmodium" question each reach a built strategy
within one clarifying exchange in replay, and the consult offers are pinned by tests. In
replay, the trypanosomatid-targets question without human (H11), the kinetoplastid core
single-copy question (H12) and the second message of the more-proteins-in-one-genome case
each reach the researcher as a card of two or three readings with the site's counts, not
as a question in words. The Lead card shows each recorded question once.
