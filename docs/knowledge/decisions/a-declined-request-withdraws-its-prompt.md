---
type: Decision
title: A declined request withdraws its prompt
description: When a model's provider declines a request on its safety filters, the turn writes data-turn-withdrawn, a typed part of protocol 2.1.0 that names the prompt; the runtime never sends that prompt to a model again, every reader drops it from the thread and shows the notice in its place, and the researcher reads which model declined, that the filters have false positives, and what to do next. Rejected - deleting the prompt's rows from the event log, and keeping the prompt in the thread.
tags: [chat, agents, protocol, providers, refusals, frontend]
generated: { by: claude-code/opus-5, at: 2026-10-09T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-10-09T00:00:00Z }
status: stable
---

# What a decline did

A provider declines a request with a refusal stop reason and no output:
Anthropic's `stop_reason: "refusal"`, which pydantic-ai maps to
`finish_reason: "content_filter"` and raises as `ContentFilterError` when the
response carries nothing else. OpenAI's content filter takes the same path.

Measured on the recorded Anthropic wire
(`tests/_support/provider_wire.py::anthropic_declining_stream`), a Lead turn on
Claude Sonnet 5.5 that met one such answer:

- wrote one `error` chunk of 1090 characters: `Content filter triggered.
  Finish reason: 'refusal', body:` followed by the whole model response as
  JSON, run id and cost included;
- replied "I stopped this turn on an error I could not recover from; what it
  answered is shown beside this reply. Send the message again and I will start
  over from it.", which asks for the one action that meets the same refusal;
- kept the prompt in the exchanges and the request text of the checkpoint, so
  every later turn sent it to the model again.

The request was sent once, and no key was marked refused: a decline is not a
retry and not a key refusal, and it stays that way.

# What was decided

**The runtime recognizes a decline; the host words it.** `assistant_core`
has `ModelDeclinedError(text, model_id)`. The emitter treats it, and a bare
`ContentFilterError`, as a decline: it writes `data-turn-withdrawn` with the
text and, for a turn opened by a prompt, that prompt's id, then the `error`
chunk with the same text. The part comes first because the AI SDK stops reading
a turn at its `error` chunk. A turn that resumes a parked call has no prompt of
its own, so its part names none and only its run is withdrawn. The one-agent graph never advances its history
past a run that raised, so the prompt is not in its next request.

**Every agent of this deployment carries the wording.**
`platform/declined.py::DeclinedRequests` is one of `agent_capabilities`, so
the Lead, FRAME, BUILD, VERIFY and site_help all turn a `ContentFilterError`
into `ModelDeclinedError`. The text names the model by its catalog name, says
the provider's biological safety filters blocked it (safety filters when the
provider names another category), says the filters have false positives, and
offers rephrasing or another model in Settings. The provider's explanation is
quoted only when it is one line of printable ASCII of 200 characters or fewer.
`ServiceRefusalRetry` and `ToolResilience` pass the error on, so a sub-agent's
decline ends the Lead's run instead of becoming a retry.

**A declined Lead turn commits nothing of its conversation**, whether it opened
on a prompt or resumed a parked call. The Lead writes no
reply, records no exchange, emits no ledger, and hands back the domain state
the turn entered with, so the request text, the intent and the open questions
of the declined prompt never reach a later instruction. The turn markers
rotate on the next message id, so finalize finds no check and writes no
memory. The parked call it answered is cleared, so no card reopens to send the same run
again. A strategy change a sub-agent landed before the decline stays on the
site and reaches the next turn as a change written outside the thread. The
thread is not named from a withdrawn prompt, an eval extract skips it, and a
fork carries the withdrawal into its own id space.

**Readers drop the prompt.** The client's snapshot reduction removes the
message the part names and reduces the turn to the part alone. Live, the web
app does the same: it removes the prompt from the chat state when the part
arrives and reduces the turn to its notice when the stream ends, puts its
words back in the composer, and forgets it as the thread's first message. The
notice renders as `FailureNotice` headed "Request declined", without the retry
button, because a retry would send the declined words again.

# Rejected

**Deleting the prompt's rows from `conversation_events`.** The log is
append-only and is the source of truth for every reader: a snapshot followed by
a tail must yield what a live reader saw. A deletion breaks that for every
client that already read the rows, leaves cursors that name nothing, and still
needs a live signal for the reader that holds the prompt on screen. A typed part
is that signal and the durable record at once.

**Keeping the prompt in the thread.** A declined prompt in the history is sent
with every later request, and the provider declines each of them, so one
declined message ends the conversation. Showing it while no model reads it
would make the thread lie about what the assistant answered.
