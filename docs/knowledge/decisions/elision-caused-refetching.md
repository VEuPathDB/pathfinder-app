---
type: Decision
title: Eliding a tool result makes the agent fetch it again
description: The context-saving elision replaced results with a stub inviting a re-call; the agent took it, and a two-criterion turn spent a large share of tool calls re-fetching identical data.
tags: [agents, cost, context, measurement]
generated: { by: claude-code/opus-5, at: 2026-08-09T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-09T00:00:00Z }
status: stable
---

# The question that started it

Was the 40K-token-per-turn bar too strict, or is the pipeline bloated?

**The bar is arithmetically impossible.** The simplest turn that can exist -- one criterion, one search, no combine -- takes 14 LLM calls, and the stable prefix alone is 4-8K tokens each. Fourteen calls times ~7K is ~98K raw input tokens before a single tool result. Observed: 101,538. A 40K bar needs about five LLM calls, which cannot do FRAME then BUILD then VERIFY.

Cost is not the issue either: $0.018 to $0.047 per turn.

# The real defect, found by looking at tool calls instead

One criterion took 8 tool calls; two took **41**. The breakdown put it in VERIFY (25 of the 41), which called `get_sample_records` four times and `get_estimated_size` three times **with byte-identical arguments**.

Cause: `KEEP_RECENT_TOOL_PAIRS = 3` elides results older than the last three pairs and replaced them with a stub reading *"re-call the tool only if you need fresh data"*. The agent took the invitation. Each re-fetch adds a pair, which elides another result, which invites another re-fetch.

It bites hardest where a phase needs more facts than the window holds. VERIFY on a three-step strategy needs at least seven.

# Two false starts worth recording

1. **"FRAME is the cost centre."** Wrong. FRAME used 16 of the 41 calls; VERIFY used 25.
2. **First A/B showed no effect.** It was run on a one-criterion query whose loop was too short to ever elide. Testing an optimization on input that never triggers it proves nothing.

A third accident proved the most useful: a rebuild silently failed, so a "no-elision" run actually re-ran unchanged code and produced **23 calls against the first run's 41**. Same query, same code, 78% variance. Single-run numbers here are noise, which is why the fix was validated on *duplicate count* -- a mechanism -- rather than on totals.

# The fix

Elision now keeps a digest instead of a stub: results at or under 400 characters are left whole (a count costs ~10 tokens to keep and a whole round trip to re-fetch), larger ones keep a 220-character head so their facts stay answerable, and the wording no longer invites a re-call.

| arm | tool calls | duplicate re-calls |
|---|---|---|
| before | 41, 23 | 12, 3 |
| elision disabled | 18, 22 | 0, 0 |
| **digest** | **22, 18** | **0, 0** |

The digest matches disabling elision outright while keeping the context compression that elision exists for.

# What the bar should be

Raw tokens conflates cached and uncached and punishes a working cache (40% of input tokens were cache reads). Measure instead:

1. **Duplicate tool calls -- should be zero.** It is a defect count, not a budget.
2. **Tool calls per criterion**, which should be flat.
3. **Cost per turn.**

And never from one run.

# Anchor

`assistant-platform: packages/assistant-core/src/assistant_core/conversation/history/elision.py`. Guarded by `assistant-platform: packages/assistant-core/tests/unit/conversation/history/test_elision.py`.
