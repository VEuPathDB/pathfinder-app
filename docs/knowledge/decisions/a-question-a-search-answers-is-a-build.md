---
type: Decision
title: A question a search answers is a build
description: A question whose answer is the size or the members of a gene search on the site is classified as a build and answered by the search, not by the literature or the web, because the step is the number's provenance and the site computes it; a question that compares counts is answered by the read-only comparison and adds no step.
tags: [lead, intent, research]
status: stable
---

# The choice

`classify_user_intent` (ai/lead/lead_tools.py) and the Lead's instructions
(ai/lead/_lead_instructions.py) name the rule: "how many genes" and "which genes" ask
for a build, whatever the grammar of the message. The turn is `new_strategy` on a thread
with no strategy and `extend_strategy` otherwise; `follow_up_question` keeps its meaning,
a request to explain something that changes no data. A question the record or the
literature answers - a product, a mechanism, a rate - stays a research question.

A question that compares counts - two strains, two searches, two values of one
parameter - is the exception: it is a `follow_up_question` answered by
`compare_search_variants`, which counts each side on the site as an anonymous report and
adds no step. The comparison card is the provenance of both numbers. FRAME's
`set_structure` holds the same rule on the tree: a UNION that joins a step the strategy
holds to an arm the turn adds is refused unless the researcher stated an OR over those
arms (`combination_check.unstated_union`), and the refusal names the comparison.

`compare_search_variants` counts each variant in place in the strategy's result, so it
takes only searches a step runs. A count of any other catalog search is `count_search`,
and "which of these genes also ..." over genes the conversation showed is
`genes_in_search` (`ai/tools/standalone/search_reads.py`): each runs one search as the
same anonymous report and adds no step. The genes it checks by default are the records
this turn's facts list, else those the latest facts part that showed records showed
(`TurnFacts.shown_before`, kept as `StrategyDomainState.shown_records`). A search name
the catalog does not list is refused with what the catalog lookup finds for it, so a
search is reported absent only when that lookup finds nothing.

# What was measured

"Compare the number of annotated protein-coding genes across P. falciparum 3D7, T. gondii
ME49 and C. parvum Iowa II, and say where the numbers come from" was classified
`follow_up_question` on both models. The Lead then made twelve to twenty web and
literature calls, ended the turn with no reply three times, and when it did answer quoted
counts from web pages. The portal catalog holds `GenesByTaxon` and `GenesByGeneType`, so
the answer is three two-step strategies whose root sizes are the counts, built and
verified by the loop the product already has.

A count compared "with the reference strain" was built as "one step per organism". A
strategy has one root, so the second step had to join the first, and an INTERSECT across
organisms is refused, so the join was a UNION: the researcher's 37-gene DAL972 answer
became an 80-gene two-strain union (round-3 dry UAT, the third instance of the class).

# What was rejected

**Answering from the web.** A page quotes a number without the search that produced it;
the site computes the number, and the step is reproducible in the UI.

**One step per compared side.** A strategy has one root, so a second side joins the
first and changes the researcher's answer; the comparison counts both sides and keeps it.

**A tool that reads organism-level statistics.** It would answer this one question and
teach nothing about the next; the search loop answers every question of this shape.
