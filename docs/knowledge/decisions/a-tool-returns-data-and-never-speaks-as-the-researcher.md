---
type: Decision
title: A tool returns data and never speaks as the researcher
description: No PathFinder tool sets ToolReturn.content, because pydantic-ai sends that field as a separate user prompt part; what the Lead does with a result is written in its instructions.
tags: [lead, tools, pydantic-ai]
status: stable
---

# The choice

A tool returns its value in `return_value` and its one summary line in the metadata. It
never sets `ToolReturn.content`. What the Lead does with a comparison, a scored
comparison or a consult's answers is written in the Lead's instructions
(ai/lead/_lead_instructions.py). A structural test walks every module of the package and
fails on a `ToolReturn(..., content=...)` or an assignment to `.content`
(tests/unit/ai/test_no_tool_speaks_as_the_researcher.py).

# What was measured

pydantic-ai 2.41 documents `ToolReturn.content` as content sent to the model as a
separate `UserPromptPart` (`pydantic_ai/messages.py`). `compare_search_variants` ended
that text with "Summarize the trade-off for the user and ask which to proceed with (no
scoring - no controls)". The Lead read it as the researcher's message: after every
comparison it classified the turn again, recorded "no scoring - no controls" as a
requirement, and ended each reply on a question the researcher never asked.

# What was rejected

**Rewording the text as data.** Any text in that field reaches the model in the user's
voice, so no wording makes it tool output.
