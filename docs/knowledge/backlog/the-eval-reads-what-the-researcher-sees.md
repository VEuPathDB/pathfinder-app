---
type: Backlog
title: The eval reads what the researcher sees
description: The corpus phrase checks match against a reply's stored markdown, where every punctuation mark is escaped, so an expected phrase with a period or a colon never matches; and two cases leave the consult cards the Lead now asks unanswered, so they end before a build.
tags: [evals, corpus, markdown, cards]
generated: { by: claude-code/opus-5.5, at: 2026-11-02T00:00:00Z }
status: proposed
---

# The eval reads what the researcher sees

## What happens

A reply is stored as markdown in which `domain/written_links.py::plain_markdown`
escapes every ASCII punctuation mark. `devtools/eval_runner.py` keeps that text
(`capture.assistant_text()`) and `evals/phrases.py` matches expected phrases against it
after case-folding and spacing only. In `uat-n7-plasmodb` the last reply is the expected
sentence, stored as `You declined the last offer\. Say what to change\, or ask me to
offer it again\.`, and the `replyMentions` check fails. Any expected phrase with
punctuation (a GO id such as `GO:0031225`) fails the same way.

`uat-dry4-b-tritrypdb` and `uat-dry-b-fungidb` run under the `leave` policy. The Lead now
asks a consult card for the zinc-finger domain entry (turns 1 and 2 of dry4) and for the
anchored-membrane GO term (turn 5 of fungidb). The cases name no answer for those cards,
so dry4 builds no strategy and fungidb keeps one step where the case expects
`(GenesByGoTerm INTERSECT GenesByOrthologPattern)`. Both fail the same way on main and on
the requirement-id branch.

## Done when

The phrase checks read the reply as the researcher sees it (the markdown escapes
removed), with a unit test on an escaped reply; dry4 and fungidb name an answer for each
card the Lead asks, recorded from a run; a corpus replay passes all three.
