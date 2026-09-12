---
type: Backlog
---

# No turn records the gene sets it created

**What I did.** Read every reference to `StrategyDomainState.created_gene_set_ids`
(`ai/graph/state.py:158`) outside the test tree.

**What I got.** Two references: the field's own declaration, and the read in
`ai/lead/memory_candidates.py:60` that turns each id into a `gene_set_note`
memory candidate. No production module appends to it. The list is empty on
every turn, so `_build_gene_set_value` runs for nothing.

**Why that's wrong.** A researcher who saves a gene set gets no note about it,
so the next session's memory retrieval cannot recall the set they built, and
`search_memory(kind="gene_set_note")` answers empty on an account that holds
gene sets.

**Why it happens.** `create_workbench_gene_set` (`ai/tools/standalone/workbench.py`)
runs under `AgentDeps`, which carries no `PipelineState`, so the tool has
nowhere to record the id it just created. The Lead's wrapper
(`ai/lead/lead_tools.py`) does hold the state, so recording there alone would
make the note appear for a Lead save and not for a VERIFY save.

**Fix.** Give the created-id record one home both registrations reach - a field
on `AgentDeps` the Lead's node folds back into `PipelineState`, the way
`apply_agent_state` already folds the discovered searches - and append to it in
the tool body, not in either wrapper.

**What you'd get.** Every gene set a turn creates leaves one `gene_set_note`
memory, whichever agent created it.
