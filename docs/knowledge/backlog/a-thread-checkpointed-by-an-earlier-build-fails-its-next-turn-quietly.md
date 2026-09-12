---
type: Backlog
---

# A thread checkpointed by an earlier build fails its next turn quietly

**What I did.** On plasmodb in the web app, sent "Save the 155 genes from this strategy as a gene set called gametocyte secreted candidates v2." on a thread (`208aee75-1d69-480d-a7c3-d309ef1c8194`) whose last turn had run under a build in which `StrategyDomainState` still declared `created_gene_set_ids` and `open_eda_sheets`; the current build declares `created_gene_sets` and `open_eda_sheet` instead.

**What I got.** The thread showed "Response failed: AttributeError: 'dict' object has no attribute 'node_results'" after 11 s. The worker traceback: `pre_turn.py:69 refresh_live_strategy_state -> staleness.py:59 detect_build_staleness: recorded = {n.node_id: n.count for n in outcome.node_results}`, where `outcome` is a plain dict. No memory note, no gene set, and every later turn on the thread fails the same way.

**Why that's wrong.** `no-checkpoint-truncation.md` chose a strict state so that a stale key fails loudly and a migration truncates the checkpoints a shape change orphans. Neither happened: the state renames shipped with no migration, and the failure is not loud. The researcher sees an attribute error from the middle of a turn and cannot tell that the conversation is dead.

**Why it happens.** `StrategyDomainState` and `PipelineState` forbid extra fields, so `cls(**stored)` raises for a checkpoint carrying a dropped key; LangGraph's checkpoint serializer (`langgraph/checkpoint/serde/jsonplus.py`, the `except Exception: return cls.model_construct(**tup[2])` fallback) then builds the model without validation, which leaves every nested record (`BuildOutcome`, the spec, the ledger records) as the mapping it was stored as. The first attribute read on one of them fails.

**Fix.** Two parts, and the second is the recorded decision's own rule. (1) The loud failure the decision wants must be the app's, since the serializer swallows the model's: at turn entry the loaded state is validated strictly (`PipelineState.model_validate(state.model_dump())` or a serializer hook that refuses the fallback), and a failure ends the turn with a typed refusal that names the cause ("this conversation was saved by an earlier version of PathFinder and cannot continue"), never an attribute error. (2) Every change to a checkpointed field ships with the migration the decision names (a truncation of the checkpoint tables, or a targeted one), listed in the pre-commit gate the way the OpenAPI freshness check is. The alternative, dropping unknown keys (`extra="ignore"`) and rebuilding the rest, reverses `no-checkpoint-truncation.md` and needs that decision reopened with this evidence; it was tried here and reverted.

**What you'd get.** A thread from before a state change either resumes (after its checkpoint was truncated by the migration, from a fresh turn) or refuses with a sentence the researcher can act on; a rename can no longer land without its migration.
