---
type: Backlog
---

# The revert dialog says the strategy graph is kept

**What I did.** On toxodb, thread `0a6715df-30e9-4336-97ed-f55ba6ca72ad` had two turns: a 7-step build (WDK 214618720, 153 genes) and an edit that raised the proteomics floor (same strategy, MassSpec step patched to 2/2, 139 genes). I edited the second message, chose Revert in the dialog, and sent a different edit.

**What I got.** The dialog reads "Delete every message after this point in this chat. Scratchpad notes and pending tasks from those turns are also removed. Strategy graph and workbench state are kept." After the 204 the thread pointed at a new WDK strategy 214618800 carrying the first turn's parameters (MassSpec 1/1, 6,811), revision 202 written by the revert itself before the replacement message; 214618720 stayed in the WDK account with the second turn's parameters.

**Why that's wrong.** The graph is not kept: it is restored to the snapshot at the reverted message, as `services/conversations/revert.py::revert_conversation_to_message` and `revision_ops.materialize_revision` ("adopt a snapshot as a strategy of the thread's own on WDK") intend. A researcher who reads "kept" expects the edit's steps to survive and finds the earlier ones.

**Why it happens.** `apps/web/src/features/conversation/content/BranchOrRevertDialog.tsx` line 63 states a rule the service does not have.

**Fix.** The sentence says what happens: "The strategy goes back to what it was at this message; a later version stays in your VEuPathDB account. Workbench gene sets are kept." Update the dialog's vitest (`RevertFlow.test.tsx`) assertion on the copy.

**What you'd get.** A dialog that tells the researcher the strategy will roll back before they confirm.
