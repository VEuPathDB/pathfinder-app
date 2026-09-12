---
type: Backlog
---

# A sub-agent that runs out of tool retries ends the turn with a canned line

**What I did.** The same portal turn as the transform card (thread `6acbbb4f-bf98-4389-9b4d-0d9e2e4e5f09`): FRAME's `set_structure` was refused three times.

**What I got.** The event log ends with `error: Tool 'set_structure' exceeded max retries count of 3. Consider raising the retry limit, or see the docs on tool retries: https://pydantic.dev/docs/ai/...`, then the Lead's prose "I couldn't produce a response for this turn. Please rephrase or provide more context and I'll try again.", `finish`, `done`. The trace shows PLANNING "Not finished". The ledger holds the four bound criteria and the three refusals; none of it reaches the reply.

**Why that's wrong.** The turn knew exactly what went wrong (a structure refused three times, with the refusal's words) and told the researcher to rephrase. A framing that stops on its call budget or on a repeated call is reported as a stop the Lead can explain (`ai/lead/phase_stop.py`); a framing that stops on retries is the same kind of event and is treated as a crash.

**Why it happens.** `ai/lead/sub_agent_stream.py` catches `UsageLimitExceeded` and the repetition guard's stop and turns them into `PhaseStop`, but pydantic-ai's `UnexpectedModelBehavior` (the exception a tool's exhausted `max_retries` raises) is caught nowhere in `ai/lead` or `ai/graph`, so it unwinds the Lead's own run, `capture.response` stays empty, and `ai/graph/lead_node.py::_run_lead_turn` substitutes the canned line.

**Fix.** A third `PhaseStopReason`, `TOOL_RETRIES` (the pass stopped after one tool refused a call N times), raised into `deps.last_phase_stop` from the same `except` ladder that handles the budget, carrying the tool name and the last refusal text; the Lead hears it the way it hears a budget stop, keeps the partial draft, and reports the refusal's words. The pydantic-ai error text (with its docs URL) never reaches the thread. Red first: a scripted FRAME whose `set_structure` is refused past its retries ends with `last_phase_stop.reason == TOOL_RETRIES` and the Lead's reply quotes the refusal.

**What you'd get.** A reply that says the structure was refused and why, and offers the change, instead of "rephrase".
