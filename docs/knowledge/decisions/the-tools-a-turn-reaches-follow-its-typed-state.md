---
type: Decision
title: The tools a turn reaches follow its typed state, never its classification
description: The Lead's classification is a typed record the turn and FRAME read, and the tools a turn reaches are decided by typed preconditions alone; withholding the building tools or the audit tools by the classification's label, refusing a reclassification and holding a classification to word heuristics were rejected.
tags: [lead, intent, tools, classification]
generated: { by: claude-code/opus-5.5, at: 2026-10-27T00:00:00Z }
status: stable
---

# What was decided

`ai/lead/intent_gate.py::tools_the_turn_offers` withholds a tool only for a typed
precondition: `unmet_preconditions` (a strategy with a step is edited, never framed
again; a build needs no strategy step; recovery needs a failed build; a check needs a step
and runs once; an EDA step needs a counted subset; a turn refused for want of a check
reaches the check alone; after a check a change waits for a card) and a turn that started
an audit, which ends. Nothing reads the classification's label to decide reach: an
unclassified turn, a question, a context statement and an off-topic message reach the
same tools, the audit tools included. A write that needs the researcher's consent stays
behind its approval card (`consult_user`, `propose_changes`, `delete_step`,
`start_gene_model_audit` and the rest), so consent does not depend on the label either.

`classify_user_intent` keeps the classification as a typed record: the turn's markers,
the requirements it states, the questions it answers, the ledger and FRAME's work order
read it. A second call replaces it. The checks that stay are typed: an operator the
message does not state, a question that asks a change or withdraws a requirement, an
answer on a conversation that asked nothing, and gene ids the message does not hold; the
same refused call sent again fails without a retry. The off-topic reply is an instruction
(two sentences, no tool), not a tool removal.

# Why

A rule audit of the recorded runs found that 40 of 45 classification refusals refused the
Lead's own reclassification, a loop the Lead's prompt then had to patch ("a missing
building tool is a misclassification"). The recorded harm: a turn whose building tools
were withheld invented search names, and a turn whose audit tools were withheld answered
an audit question wrongly. No recorded run shows the withholding preventing an error.
Every error the harness caught came from typed state and the site's own answers.

# Rejected

- **Withholding the building and audit tools until a building or audit label.** It makes
  a wrong label a wrong turn, and the model cannot see why a tool is missing.
- **Refusing a reclassification after the turn wrote, or a repeated one.** It froze a
  wrong label in place; a later write keeps the work the turn did without it.
- **Word heuristics over the message (check words, an organism and a gene class, a
  record-type name, words outside the asks).** They held the classification to phrasing.

# What would prove this wrong

`tests/unit/ai/lead/test_intent_gate.py` holds every classification, and none, to the same
building tools on a fresh thread and the gene record read; `tests/unit/ai/lead/test_the_lead_audits.py`
holds every classification to the audit tools and a started audit to none.
