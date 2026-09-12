---
type: Backlog
---

# A dispatch and the Lead's own durable call cannot both be parked

**What I did.** Built the Lead response the saved-set enrichment makes reachable: one
`verify_strategy` dispatch whose sub-agent parked its own gated `run_gene_set_enrichment`,
and beside it the Lead's own `run_gene_set_enrichment` on a saved set, then called
`ai/graph/_lead_turn.py::pending_durable_call` on it
(`tests/unit/ai/graph/test_durable_resumption.py::test_a_dispatch_and_a_lead_durable_call_in_one_response_are_refused`).

**What I got.** Before the refusal landed, `pending_durable_call` returned the parked
dispatch and dropped the Lead's own call: `dispatches` is collected first and returned
before `own` is read, so `parked.durable_calls` held the sub-agent's inner call only. The
Lead's task row exists and its job runs. Now the same input raises
`UnparkedDurableCallError`, naming the dropped call id.

**Why that's wrong.** Two tasks are deferred and only one can be answered. The dropped
call's task reports, `PendingDurableCall.owns(task_id)` matches nothing, and pydantic-ai
re-executes a deferred call it is given no result for, so the same 120-second enrichment
runs a second time and the turn can loop. The refusal stops the double charge and costs the
turn: both jobs are already deferred when it raises, so the researcher gets an error instead
of the two answers they asked for and two task rows stay `running` in the rail with nothing
left to close them. The text they read is the defect wording every internal stop gets, and
it stays provisional until the calls are answered instead of refused.

**Why it happens.** `_resume_durable_call` (`ai/graph/_lead_turn.py`) hands every entry of
`parked.durable_calls` to the sub-agent's suspended run: it calls `durable_tool_results` for
the whole list and passes the result to `resume_sub_agent`, then answers the Lead with the
dispatch's own outcome alone. A call the Lead made itself has nowhere to sit in that path,
so `pending_durable_call` refuses the pair rather than parking a list half of which would be
misrouted. Nothing in the runtime forbids the mixed list: `PendingDurableCall.durable_calls`
is `Field(min_length=1)` with no upper bound and no ownership field,
`task_ids` and `owns` mean "every task this park waits on", and `answered_durable_call`
already withholds the resume until every one of them has reported. The misrouting is this
repository's resume logic, not the runtime's shape.

**Fix.** Partition the answers app-side, which needs no new field anywhere.
`parked.sub_agent.approvals` carries the `tool_call_id` of every call the sub-agent parked
(`_inner_durable_calls` already builds from that field), so it is the discriminator at
resume time. In `_resume_durable_call`, split the `DeferredToolResults` that
`durable_tool_results` returns on that id set: resume the sub-agent with its half, and merge
the other half into the `DeferredToolResults` the Lead resumes with, beside
`{parked.tool_call_id: outcome}`. `pending_durable_call` then builds one park carrying both
groups through `parked_durable_call(..., durable_calls=inner + own, sub_agent=...)` and
`UnparkedDurableCallError` goes. One case the split must carry: when the resumed sub-agent
parks again, `_reparked` rebuilds the park from the sub-agent's new calls only, so the
Lead's already-answered calls have to travel with it or be answered on that turn.

The alternative is a runtime change: give `PendingDurableCall` a second group for the outer
run's calls and widen
`assistant_core/graph/approvals.py::parked_durable_call`, the constructor that builds it.
It is recorded and not taken: `PendingDurableCall` is checkpointed state, so a new field
changes the shape of every saved turn, and it buys nothing the app-side split does not
already have, at the cost of a library release and a re-pin.

**What you'd get.** "Build this and run GO enrichment on my saved set" ends one turn with
both tasks parked, and the completion turn answers both calls once.
