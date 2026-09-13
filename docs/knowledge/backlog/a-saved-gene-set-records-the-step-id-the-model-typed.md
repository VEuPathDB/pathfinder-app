---
type: Backlog
---

# A saved gene set records the step id the model typed

**What I did.** On plasmodb, thread `1de12b21-cdf1-43ce-ac5d-cd3b8a4a4720` (a 9-step strategy, WDK 214618620, root step 227253270, 3 genes): "Save the current result as a gene set named 'essential kinase candidates'." Later, on the same thread: run the control tests, then a GO enrichment on that gene set.

**What I got.** The save call was `create_workbench_gene_set(name="essential kinase candidates", gene_ids=[PF3D7_0726200, PF3D7_1039000, PF3D7_1145200], wdk_source={"wdk_step_id": 70056735, "wdk_strategy_id": 214618620})`, and the row holds `wdk_step_id = 70056735`. That is the graph's local step id `step_70056735` with its prefix stripped; the WDK root step is 227253270. The enrichment task then asked VEuPathDB for that step and failed: "POST /users/1216062453/steps/70056735/reports/standard -> HTTP 404: Resource 'Step ID 70056735' does not exist." On vectorbase, thread `601be8e2`, a set saved on a thread that never built a strategy holds `wdk_strategy_id 330643113, wdk_step_id 440433923`, ids the model supplied from nowhere the thread holds.

**Why that's wrong.** A strategy-backed gene set is the workbench's link back to the result it came from: enrichment, the results table and "re-take from strategy" all read that step. A set that names a step that does not exist fails every one of them, and nothing warned at save time.

**Why it happens.** `ai/lead/lead_tools.py::create_workbench_gene_set` takes `wdk_source: WdkSourceSpec` from the model and `ai/tools/standalone/workbench.py` writes `wdk_step_id=src.wdk_step_id` as given. The WDK ids the strategy actually has are in the session's sync state (`services/strategies/sync_state.py::wdk_step_ids`, keyed by the local step id), and the tool never reads them.

**Fix.** The tool takes the local step id (or none, meaning the strategy root) and resolves the WDK strategy and step ids from the live sync state itself; a model-supplied WDK id is not a parameter. A step the sync state does not hold is refused with the steps it does. Red first: saving from `step_70056735` records `wdk_step_id 227253270`; saving on a thread with no strategy records no WDK ids and says the set is a pasted one.

**What you'd get.** The saved set points at the real step, and enrichment, the results table and re-take work on it.
