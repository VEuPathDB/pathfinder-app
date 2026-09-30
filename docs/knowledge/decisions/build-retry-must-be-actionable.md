---
type: Decision
title: A retry must be something the model can act on
description: A refusal is a correction, or names the exact alternative, and an identical resubmission fails. build_strategy answering "call frame_problem first" when only the user could unblock was the first case; refusal sentences alone, a generic cache of reads and an enum on the search choice's term were rejected.
tags: [agents, error-messages, frame, refusals]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# What was wrong

`build_strategy` guarded with a single branch:

```python
if spec is None or not spec.ready_to_build:
    raise ModelRetry(
        "OperationalSpec is not ready to build (no criteria/structure, or "
        "open param slots need user input). Call frame_problem first."
    )
```

One message for two unrelated situations. Seen on a real multi-criterion drug-target build: FRAME bound **all 8 criteria** and left **7 open parameter slots** with `needs_user`. The Lead called build anyway and got told to run FRAME again -- which regenerates the same slots, because only the user can supply them.

A `ModelRetry` says "you can fix this yourself and try again". That is true when no spec exists. It is false when a human has to answer, and stating it anyway invites a loop.

# The fix

`build_not_ready_message(spec)` answers by case:

- **no spec, no criteria, or no structure** - "call frame_problem first", which the model can act on;
- **open slots** - names each parameter, carries FRAME's question and options, and says explicitly *do not re-frame, ask the user*;
- **unbound criteria** - names them and sends the model back to FRAME to bind;
- **criterion-level open params** - names them and says to ask.

The guard still raises `ModelRetry`; only the wording varies. That keeps the existing control flow while removing the instruction that caused the loop.

# The invariant every tool refusal holds

A refusal is one of three things, in this order:

- **A correction, when the code can compute it.** `set_criterion` leaves out a
  parameter only the site sets (read-only, or hidden with no vocabulary:
  `document_type`, `dataset_url`) proposed at the value the site holds and
  names it in `corrections`; it maps a
  display name written without its parenthetical ("Text term") or in other case
  and punctuation to the parameter; a value edit on the search a criterion
  already runs keeps the held reason, with or without a `why`, and needs no
  catalog read, while that reason names no value the edit replaces; one that
  does is refused naming the value unless the call carries a `why`, which is
  then recorded against the catalog read the held reason came from. An
  overview is a catalog read itself, so it takes any name the site holds.
- **A refusal that names the exact alternative.** A parameter only the site
  sets, at another value, names the value the site holds and the names `params` takes; a phrase
  the bound search does not hold names the words its name and description do
  hold. A search variant that sets a parameter its search does not take names
  the parameters the search takes. The schema carries what the model fills: `Tool.prepare` on
  `set_criterion` keys `params` by the open sheets' parameter names and lists
  their display names in the description of `why.term`, and the sample cap is
  `le=100` on `get_sample_records.limit`.
- **A failure, when the same call comes back.** A call refused and sent again
  with the same arguments before any call has run fails as `ToolFailed` with the
  refusal, without running and without spending a retry. A refused call has not
  run, so other refusals between the two do not release it. Sent a third time it is
  the refusal again as `ModelRetry`, which the library counts against the tool's
  retries, so a loop ends the pass. The trace draws the failed call as an error
  row, as it draws a refusal (`ai/lead/sub_agent_events.py::_step_state`), since
  the call did not run. A control test repeated on a step answers
  once from the turn's record; the second repeat fails naming every step tested
  and what its controls returned.
- **A refusal on the last attempt is an answer.** An edit whose framing pass is
  refused on the last attempt the tool allows ends with disposition `unbound`:
  nothing is applied, the refusal is the facts' refusal row, and the reply
  names what could not be bound. A resend prompt from a spent retry budget
  tells the researcher nothing the refusal did not.
- **One check has one sample.** The sample's offsets are drawn from a seed of
  the step and the revision of what the step computes, so an identical sample
  call answers the same records, in this message or a later one, and a read of
  them is the repeat the record budget refuses by name. A step whose search,
  values or inputs change draws a new sample. A read of the step's ids with a
  limit draws the same offsets (`results.step_sample_seed`), so five ids and a
  sample of five are the same five genes; a read with no limit keeps the site's
  order.
- **A budget is a refusal like any other.** A check's record read past its
  budget, or of a record it already read, is a `ModelRetry` naming the records
  already read and `read_step_columns`
  (`ai/tools/standalone/gene_record.py::read_sampled_gene_record`), so the
  refusal memory holds it and the trace draws it failed.

The schema changes only when a sheet opens or closes, which is when the pinned
sheets in the instructions change too, so the prompt cache loses nothing it
would have kept.

## Rejected

- **Refusal sentences alone.** Each named the rule and not the fix, so the model
  sent the call again with nothing the refusal named changed.
- **The runtime guard's cap on record reads.** It answers a read past its cap
  with a normal result, which the refusal memory never sees and the trace
  records as completed, and its text names the wrong alternative.
- **A cache of identical reads.** A strategy can change between two reads, so a
  replayed answer would be wrong; a sample is seeded instead, so the same call
  on the same step reads the same records from the step as it stands.
- **A seed of the message and the step.** It rotated the sample on every
  message, so a researcher who asked for the same sample again was shown other
  genes from a step whose answer had not changed. The reads
  that looped already answer from a record the turn holds: the overview's
  already-read notice and the control test's record.
- **An enum on `why.term`.** The organism, only-match and nearest bases take a
  value or a phrase of the request no sheet lists, so an enum would refuse three
  of the five bases; the display names are listed and their variants corrected.

# What this did not fix

The turn that exposed it also died with an OpenAI `No tool invocation found for tool call ID` error. That crash **recurred on a re-run that never reached BUILD**, so it is independent and is tracked separately in the backlog. Fixing the message was worth doing on its own merits; it was not the crash.

# Anchor

`build_not_ready_message` in `ai/lead/sub_agent_dispatch.py`. Guarded by `tests/unit/ai/lead/test_dispatch_messages.py`, which asserts the open-slot message never says "frame_problem".

The invariant: `ai/tools/toolsets/_refusals.py::RefusalMemoryToolset`, which
wraps the Lead's own tools and sweep (`ai/lead/lead_agent.py::build_lead_toolset`)
and the FRAME, VERIFY, execution and EDA toolsets,
`ai/tools/standalone/_frame_schema.py::name_the_open_sheets`,
`_frame_proposals.py::left_to_the_site`, `_frame_rationale_terms.py::_headed_by`,
`_frame_rationale.py::rationale_for`, `experiment.py::_answered_from_this_message`.
Guarded by `tests/unit/ai/tools/test_a_refusal_is_a_correction.py`,
`tests/unit/ai/tools/toolsets/test_a_refused_call_is_not_run_twice.py`,
`tests/unit/ai/lead/test_a_refused_lead_call_is_not_run_twice.py`,
`tests/unit/ai/tools/toolsets/test_the_bind_schema_names_the_sheet.py` and
`tests/unit/ai/lead/test_repeated_control_tests_on_one_step.py`.
