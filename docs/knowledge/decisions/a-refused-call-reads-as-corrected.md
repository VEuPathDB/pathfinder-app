---
type: Decision
title: A refused call reads as corrected, not as a failure
description: A tool call handed back to the model to send again, by a model retry or by a guardrail that raises CallRefused, carries a corrected tool summary and draws a grey retried row; a call the site or the code failed keeps the red error row. Matching the error text in the browser, turning refusals into ordinary outputs and treating every error as corrected were rejected.
tags: [thread, trace, tools, protocol, guardrails]
generated: { by: claude-code/opus-5.5, at: 2026-10-17T00:00:00Z }
status: stable
---

# What was decided

A call the model sent wrong and is told to send again is not a failure, and the trace says
so. Protocol 2.2.0 lets a failed call's `data-tool-summary` carry `status: "corrected"`
(`assistant_core/PROTOCOL.md`, section 6.3), and two producers write it:

- **Every model retry.** The runtime's event stream writes the summary after each
  `RetryPromptPart`, with the reason as its line. No tool here, in `veupathdb_mcp` or in
  the runtime turns a site or network error into `ModelRetry`, so a retry is always the
  model's call handed back.
- **Every guardrail that refuses a call without spending a retry.** It raises
  `CallRefused` (`assistant_core.capabilities.refused_calls`), a `ToolFailed`, and
  `MarkRefusedCalls`, which `agent_capabilities` gives every agent, carries the summary on
  the failed result. The read-once and refused-call toolsets, the Lead's classification
  gate, the edit and delete rules, the check's record budget and a repeated control test
  raise it.

A read the site broke off, timed out or refused (`ai/capabilities/site_reads.py`) stays a
plain `ToolFailed` and draws the red X, and so does a turn that failed. The client reads a
corrected call as row status `corrected` (`@veupathdb/assistant-client`), and a
sub-agent's step as state `corrected` (`ai/lead/sub_agent_events.py`); `TraceRow` draws a
grey retry glyph with the reason as the row's line.

# What would falsify this

A row drawn as corrected whose call failed because the site or the code did, or a red row
whose call a guardrail refused as sent.

# What was rejected

**Reading the error text in the browser.** A list of phrases that mean "the model sent it
wrong" breaks the first time a message is reworded, and the browser cannot tell a site's
refusal from a guardrail's.

**Refusals as ordinary outputs.** Protocol 1.2.1 does this for the repetition guard. Here
it would change what the model reads, a result instead of a failed call, and a
`ModelRetry` that stops being one stops counting against the tool's retry budget, which
ends a loop.

**Every error as corrected unless marked a failure.** A failure nobody marked would read
as the model's mistake. Failure stays the default, and each correction says it is one.
