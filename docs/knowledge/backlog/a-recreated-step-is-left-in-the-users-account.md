---
type: Backlog
---

# A recreated step is left in the user's VEuPathDB account

**What I did.** On plasmodb, replaced the search of one step of a two-leaf strategy (`replace_subtree` over `step_a`, `GenesByRNASeqpfal3D7_Su_seven_stages_rnaSeq_RSRC` -> `GenesByMicroarrayBirkholtz`). The push planner recreates the leaf and every combine above it, and the strategy is re-rooted onto the new steps.

**What I got.** The session's `wdk_step_ids` names only the new steps. The old leaf (440432473) and the old combine stay in the account as steps that belong to no strategy: `delete_orphaned_steps` is driven only by `dropped_step_ids` (`services/strategies/commit.py`), and a recreate drops no local step, so their ids are never passed to it.

**Why that's wrong.** Every search change and every operator change leaves two more unreachable steps behind on the researcher's account. Nothing in the app lists them and nothing records that they exist, so a long thread quietly grows a set of steps only the WDK site itself can show.

**Why it happens.** `_execute_recreate` (`services/strategies/step_wdk_push.py`) pops the old WDK id from `wdk_step_ids` before creating the new step, so the old id is forgotten rather than handed to the delete pass.

**Fix.** Carry the popped ids out of the push as recreated-and-orphaned ids and delete them in the same pass that deletes the ids of dropped steps, after the strategy's step tree is put (the put is what orphans them). Red first on the push, asserting the old id reaches `delete_orphaned_steps` and the new one does not.

**What you'd get.** A search change leaves the account holding exactly the steps the strategy uses.
