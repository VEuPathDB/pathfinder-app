---
type: Decision
title: An off-topic turn reaches no tool
description: The classification the Lead makes first is what puts a request outside PathFinder's scope, and that turn is offered no tool, is pinned a two-sentence redirect, is refused if it answers anyway, and stops at a token ceiling of its own. A prompt-only redirect, a pre-turn topic classifier and lowering the run's live UsageLimits were rejected.
tags: [agents, intent, scope, budget]
generated: { by: claude-code/opus-5, at: 2026-09-13T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-13T00:00:00Z }
status: stable
---

# What was decided

**`off_topic` is load-bearing.** It was a value of `IntentClassification` that
nothing read. Four things read it now, and they are all downstream of the one
call the Lead makes first.

**The tool list is empty.** `intent_gate.apply_tool_preconditions` filters the
offered tools by `OFF_TOPIC_TOOLS`, which holds nothing, so the turn's only
remaining move is its own reply. The two reads a question needs
(`read_ledger_section`, `get_live_strategy_state`) stay on the list for every
other classification.

**The pin adds the redirect to the turn briefing.** `lead_pins.pinned_turn_briefing`
renders what moved on the thread and then the redirect: two sentences, what
PathFinder does, an invitation to rephrase, nothing else. The catch-up keeps
its place because one of its sections is windowed on the newest assistant
message (`services/conversations/thread_activity.py`): a task that finished
before an off-topic turn falls out of the next turn's window, so a turn that
dropped the briefing would drop that news for good.

**The reply is bounded.** The `refuse_an_off_topic_essay` output validator
refuses, once per turn, a reply that carries a fenced code block or passes
`OFF_TOPIC_REPLY_MAX_CHARS`. A gate cannot compel prose, so the cap is checked
where the prose is.

**The turn has a token ceiling.** `Settings.lead_turn_token_limit` (600000) is
what the Lead's own run may spend in one turn, enforced by pydantic-ai through
the `UsageLimits` each turn builds. It does not cover a sub-agent pass: FRAME,
BUILD and VERIFY each run with a `RunUsage` of their own under
`phase_usage_limits`, and their tokens reach the turn total through
`_lead_capture`, not through this ceiling.

**An out-of-scope turn stops at 40000 tokens.** `off_topic_budget_stop` reads
the `RunUsage` the turn handed the run, once per streamed event, and the turn
ends itself with the budget sentence when an off-topic classification has
passed `OFF_TOPIC_TURN_TOKEN_LIMIT`. It is the same exit the repetition guard
uses: the event generator returns, so the emitter closes the stream and the
reply the turn holds is the one the user reads.

**The scope line has one home.** The classifier's own criteria are in the
docstring of `classify_user_intent`, which is what the model reads when it
classifies. The Lead's instructions state the consequence and point at it. The
scope prose is gone from `safety.md`, which the Lead never read; its refusals
stay, because a refusal to run code is not the same rule as a classification
that a request for code is out of scope, and the three phase agents that hold
the write tools read `safety.md` and not the Lead's instructions.

# What was rejected

**A prompt-only redirect.** This is what was there: `safety.md` said "politely
redirect", and the whole Lead answered the turn - every pinned sheet, the
ledger, the full tool list, and the freedom to write whatever it liked. The
request is classified either way, so the classification is free; spending a
strategy turn's context on it after that is not.

**Lowering the run's live `UsageLimits` mid-run.** `RunContext.usage_limits`
is the object the run enforces against, and mutating a field on it does change
what later requests are judged by. Its own docstring says to treat it as
read-only, so the ceiling would rest on a field the library reserves the right
to copy. Reading `RunUsage` costs one comparison per event and asks the library
for nothing it does not publish.

**A pre-turn topic classifier.** A separate model call before the Lead, over
the message alone. It cannot see the thread, and the thread is what decides
these cases: "run it again", "yes, do that", "which of these are kinases" all
carry no VEuPathDB object of their own. `classify_user_intent` runs inside the
turn with the ledger and the pinned state, and it already exists.

**Keeping `classify_user_intent` on the list for an off-topic turn.** It would
let the model correct itself the way a misclassified build does. It also
leaves the loop the empty tool list closes. The correction path a build has is
worth its cost because the alternative is a refusal to do work the user asked
for; here the alternative is one reply the user can answer with a rephrase.

# What is not measured here

The classifier's false-positive rate on real biology prompts. Every test in
this repository drives the scripted model, which classifies by string marker,
so nothing here says how often a real model calls a real question out of scope.
The cost model above rests on that rate being low and on the failure being
cheap (two sentences, one rephrase, nothing built or saved wrongly). The rate
is measured live at acceptance, not by the suite.

# What the reader can check

`tests/unit/ai/lead/test_intent_gate.py`, `test_off_topic_reply.py`,
`test_lead_pins.py`, `test_turn_budget.py`,
`tests/unit/ai/graph/test_lead_turn_budget.py`, and
`tests/integration/ai/test_off_topic_turn.py`, which drives the real Lead over
the scripted model and reads the two tool calls the turn makes.
