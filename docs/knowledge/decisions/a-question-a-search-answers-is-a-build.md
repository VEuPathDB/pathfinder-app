---
type: Decision
title: A question a search answers is a build
description: A question whose answer is the size or the members of a gene search on the site is classified as a build and answered by the search, not by the literature or the web, because the step is the number's provenance and the site computes it.
tags: [lead, intent, research]
status: stable
---

# The choice

`classify_user_intent` (ai/lead/lead_tools.py) and the Lead's instructions
(ai/lead/_lead_instructions.py) name the rule: "how many genes", "which genes" and a
count compared across organisms ask for a build, whatever the grammar of the message.
The turn is `new_strategy` on a thread with no strategy and `extend_strategy` otherwise;
`follow_up_question` keeps its meaning, a request to explain something that changes no
data. A question the record or the literature answers - a product, a mechanism, a rate -
stays a research question.

# What was measured

"Compare the number of annotated protein-coding genes across P. falciparum 3D7, T. gondii
ME49 and C. parvum Iowa II, and say where the numbers come from" was classified
`follow_up_question` on both models. The Lead then made twelve to twenty web and
literature calls, ended the turn with no reply three times, and when it did answer quoted
counts from web pages. The portal catalog holds `GenesByTaxon` and `GenesByGeneType`, so
the answer is three two-step strategies whose root sizes are the counts, built and
verified by the loop the product already has.

# What was rejected

**Answering from the web.** A page quotes a number without the search that produced it;
the site computes the number, and the step is reproducible in the UI.

**A tool that reads organism-level statistics.** It would answer this one question and
teach nothing about the next; the search loop answers every question of this shape.
