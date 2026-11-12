---
type: Decision
title: The tools a turn reaches follow its typed state, never its classification
description: The Lead's classification is a typed record the turn and FRAME read, and the tools a turn reaches are decided by typed preconditions alone; withholding the building tools by the classification's label, refusing a reclassification and holding a classification to word heuristics were rejected.
tags: [lead, intent, tools, classification]
generated: { by: claude-code/opus-5.5, at: 2026-10-27T00:00:00Z }
status: stable
---

# What was decided

`ai/lead/intent_gate.py::tools_the_turn_offers` withholds a tool only for a typed
precondition: `unmet_preconditions` (a strategy with a step is edited, never framed
again; a build needs no strategy step; recovery needs a failed build; a check needs a step
and runs once; an EDA step needs a counted subset; a turn refused by `unverified_build`
reaches the check alone, and a refusal by any other rule narrows nothing; after a check a
change waits for a card). Nothing reads the
classification's label to decide reach: an unclassified turn, a question, a context
statement and an off-topic message reach the same tools. A write that needs the
researcher's consent stays behind its approval card (`consult_user`, `propose_changes`,
`delete_step` and the rest), so consent does not depend on the label either. The Lead
holds no audit tool ([audits are offered on the dev sites only](audits-are-offered-on-the-dev-sites-only.md)).

The classification is a typed record: the turn's markers, the requirements it states,
the questions it answers, the ledger and FRAME's work order read it. It is read from the
message before the Lead runs ([A message is read before the Lead runs](a-message-is-read-before-the-lead.md)).
The off-topic reply is an instruction (two sentences, no tool), not a tool removal, in Build
and in Explore.

# Why

A rule audit of the recorded runs found that 40 of 45 classification refusals refused the
Lead's own reclassification, a loop the Lead's prompt then had to patch ("a missing
building tool is a misclassification"). The recorded harm: a turn whose building tools
were withheld invented search names, and a turn whose audit tools were withheld answered
an audit question wrongly. No recorded run shows the withholding preventing an error.
Every error the harness caught came from typed state and the site's own answers.

# Rejected

- **Withholding the building tools until a building label.** It makes
  a wrong label a wrong turn, and the model cannot see why a tool is missing.
- **Refusing a reclassification after the turn wrote, or a repeated one.** It froze a
  wrong label in place; a later write keeps the work the turn did without it.
- **Word heuristics over the message (check words, an organism and a gene class, a
  record-type name, words outside the asks).** They held the classification to phrasing.

# What would prove this wrong

`tests/unit/ai/lead/test_intent_gate.py` holds every classification, and none, to the same
building tools on a fresh thread and the gene record read.
