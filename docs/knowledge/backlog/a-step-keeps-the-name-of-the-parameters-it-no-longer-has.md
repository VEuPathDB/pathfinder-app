---
type: Backlog
---

# A step keeps the name of the parameters it no longer has

**What I did.** On toxodb, thread `aaf2042b-60dc-425c-bac2-d783002ae16b` (an 11-step invasion-protein strategy, WDK 214618850). In the strategy editor I opened the transmembrane step, changed "maximum number of transmembrane domains" from 7 to 2, and pressed Save.

**What I got.** The write reached VEuPathDB: step 227254860 now carries `max_tm: "2"`, its size moved from 23,471 to 16,829, the union above it from 29,755 to 23,471, and the root from 40 to 26. The step's name did not move: the node in the graph still reads "Genes with 1 to 7 predicted transmembrane domains across all Toxoplasma", and WDK's own `customName` for the step is still "Genes with 1 to 7 predicted transmembrane domains across all". A researcher reading the graph, or the strategy in VEuPathDB's own workspace, sees a criterion the step no longer applies.

**Why that's wrong.** The name is how a step states what it asks; a name that contradicts the parameters is worse than no name, and it travels: it is written into the researcher's VEuPathDB account and appears in every later view of that strategy.

**Why it happens.** The step's name and its parameters are written by different operations. `UpdateStepParamsOp` (`domain/strategy/operations/types.py`) carries only `parameters` and `_apply_update_step_params` leaves `display_name` alone; only `UpdateStepMetaOp` renames, and the editor's save emits no such op. The push writes `custom_name=step.display_name` (`services/strategies/_wdk_step_calls.py`) from the unchanged name.

**Fix.** A step's name is derived from what the step asks, not stored beside it: the name a push writes comes from the criterion's sheet and current parameters (the same rendering that produced "Genes with 1 to 7 predicted transmembrane domains" in the first place), so any write of parameters carries the matching name. A name the researcher typed themselves stays theirs: `UpdateStepMetaOp` sets an explicit name that later parameter writes do not overwrite (a flag on the step, not a guess from the text). Red first: applying `UpdateStepParamsOp` with `max_tm` 2 to a step named for 1 to 7 leaves a name that states 1 to 2, and applying it to a step with an explicit name leaves that name alone.

**What you'd get.** After the edit the node reads "Genes with 1 to 2 predicted transmembrane domains across all Toxoplasma", and so does the strategy in VEuPathDB.
