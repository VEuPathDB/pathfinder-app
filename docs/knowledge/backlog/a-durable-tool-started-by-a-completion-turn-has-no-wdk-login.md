---
type: Backlog
---

# A completion turn runs with no WDK login

**What I did.** On plasmodb, thread `1de12b21-cdf1-43ce-ac5d-cd3b8a4a4720` (a 9-step strategy, 3 genes, and a saved gene set): "Run the control tests on the final step of this strategy, and at the same time run a GO enrichment on the gene set 'essential kinase candidates'. Report both when they finish."

**What I got.** The first turn started `run_control_tests_on_step` (task `d046fca8-61ec-4bae-986f-316d27741a83`, created 19:59:22) and parked. That task completed ("3 of 3 positive controls recovered"), the completion turn opened, and from that turn VERIFY started `geneset_enrichment` (task `50c8619b-6e42-4094-8d09-45bc81e7e971`, created 19:59:37), which failed: "VEuPathDB login required: VEuPathDB serves registered users only, and this request carried no registered VEuPathDB token." The reply told the researcher to sign in and try again, in a session where they were signed in and where the control tests had just run against the same account.

**And again, on another site.** On vectorbase, thread `601425b5-1cee-47da-8b7e-5c2c3a835d4d`: "Find Anopheles gambiae genes that are upregulated in hemocytes after Plasmodium infection and that encode a predicted secreted protein. Save the result as a gene set." The first turn started `run_eda_compute` and parked; the task failed on its own arguments; the completion turn opened, called `describe_eda_study`, and that call raised the same login error, so the turn ended with "I couldn't produce a response for this turn. Please rephrase or provide more context and I'll try again." Not only a durable call: every WDK-backed tool in a completion turn is unauthenticated.

**Why that's wrong.** The researcher asked for two analyses in one message; the second is refused for a login they have, and the advice they get cannot fix it. Every turn that follows a durable task is affected, and a completion turn is exactly where an agent reads a result and starts the next analysis.

**Why it happens.** In the runtime (`assistant-platform: packages/assistant-core/src/assistant_core/tasks/runner.py`), the job body runs inside `carried.restore(...)`, which reinstates the token PathFinder captured at the call (`jobs/job_context.py::WdkJobContext`); `_answer_and_settle`, which opens the completion turn, is called after that block closes, so the completion turn and every durable call it makes run with `veupathdb_auth_token_ctx` unset, and the new job captures `None`.

**Fix.** The completion turn runs inside the same carried context as the body: `_answer_and_settle` moves inside the `carried.restore(...)` block (or the block is reopened around it), so a durable call the completion turn makes captures the same credential the first call carried. Red first, in the runtime: a durable job whose carried state holds a value, whose completion turn calls the same durable tool again, defers a second job whose captured state holds that value; today it holds nothing. PathFinder's own regression: the enrichment task started by a completion turn reaches the WDK client with the token.

**What you'd get.** Both analyses run: the control test reports 3 of 3, and the enrichment returns its ranked GO terms in the same thread.
