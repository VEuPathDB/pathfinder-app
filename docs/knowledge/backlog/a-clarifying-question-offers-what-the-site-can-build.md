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
site can approximate the request
([a copy-number comparison between clades is built in bands](a-copy-number-comparison-between-clades-is-built-in-bands.md)).

## Change

1. A consult that the Lead or FRAME raises offers two or three readings it can build,
   each one line: what it means biologically, what the strategy does, roughly what it
   returns or what it misses; the user picks one or answers freely.
2. The readings come from what the catalog can express (the phyletic grammar, transforms,
   counts, the per-step count `count_step_by_column`), so a reading offered is a reading
   the turn can build.
3. An answer in the user's terms (for example "2-5 copies, at least 2x more") is mapped to
   the closest buildable reading, stated back in one sentence, and built; the turn does
   not ask again for the same thing in parameter terms.
4. A request that no reading can approximate says so once, with the reason and the
   nearest thing it can build.
5. A Lead question that rewords a recorded one without its requirement id shows beside it.

## Related

An "all" over many genomes that is asked about, and
[a copy-number comparison between clades is built in bands](a-copy-number-comparison-between-clades-is-built-in-bands.md),
are two cases of this rule.

## Where it stands

Changes 1 to 3 are in: an open slot is asked with readings
(`domain/strategy/question_options.py`, `ai/lead/recorded_cards.py`), pinned by
`test_a_question_about_a_value_offers_readings.py`. Asking first is the model's call, so
the corpus cases `orthomcl-expanded-families-question-offers-readings` and
`orthomcl-all-plasmodium-asks-which-all` accept a question or a stated reading, and the
facts state what the built count counts
([a long expression reads by what it counts](../decisions/a-long-expression-reads-by-what-it-counts.md)).
Change 4 has no code. Change 5 is open: `recorded_cards.the_card_asked` drops a
Lead question only when its prompt or requirement id matches, and a test pins the
duplicate. None of the replays below is recorded.

## Live 2026-11-02

Replayed on QA OrthoMCL with Luna, one case at a time:
- `orthomcl-expanded-families-question-offers-readings` built `GroupsByNameList`
  (7,364 groups) with no card.
- `orthomcl-all-plasmodium-asks-which-all` built `GroupsByPhyleticPattern` (797 groups)
  with no card.
- `orthomcl-all-plasmodium-every-species-reading` built one sum over every Plasmodium
  genome (`padl+pber+...>=1T`, 395 groups) where the reading is one term per species.
- `orthomcl-more-proteins-in-one-genome-than-another` built 3,896 groups and was not
  verified.

## Done when

The copy-number question and the "all Plasmodium" question each reach a built strategy
in replay, with or without one clarifying exchange, and the consult offers are pinned by
tests. In
replay, the trypanosomatid-targets question without human (H11), the kinetoplastid core
single-copy question (H12) and the second message of the more-proteins-in-one-genome case
each reach the researcher as a card of two or three readings with the site's counts, not
as a question in words. The Lead card shows each recorded question once.
