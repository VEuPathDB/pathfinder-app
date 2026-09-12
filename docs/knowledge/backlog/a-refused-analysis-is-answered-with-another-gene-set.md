---
type: Backlog
---

# A refused analysis is answered with another gene set

**What I did.** The same turn as the pasted-set card, thread `acc48b9e-8440-45b4-bb2c-36a4280ff7ee`: enrichment on "gametocyte secreted candidates v3", then a CSV export of it.

**What I got.** Four `run_gene_set_enrichment` calls. The first two named the set the researcher asked for (`1a52f8ea`, source paste), and its task failed on validation. The next two named a different set, `3fd2604b`, "WDK Strategy 214617320" (155 genes, source strategy), whose task completed. The reply opens "Completed the GO enrichment for **'gametocyte secreted candidates v3'** (155 genes analyzed)" and lists that other set's terms. Nothing in the reply says the first attempt failed or that a different gene set was analysed.

**Why that's wrong.** The researcher asked about one saved set and was given another set's analysis under the first one's name. Here the two happen to hold the same 155 ids, so the numbers are right by luck; the next pair of similarly named sets will not be, and the thread carries no record that a substitution happened.

**Why it happens.** A durable task that fails reports its error to the completion turn, and nothing in the Lead's instructions says a failed analysis is reported, not routed around: the model treated the failure as a reason to try a neighbouring set. The reply then names the set the request named, because that is what the request said.

**Fix.** A failed durable task is a fact the turn states: the Lead's instruction for a task that reports `status: failed` is to say which analysis failed and why, and to ask before running the same analysis on a different object. The turn's reply names the gene set the analysis actually ran on, by id, whenever it is not the one the request named. Red first: a mock turn whose first enrichment task fails and whose second succeeds on another set produces a reply that states the failure and names the set that was analysed.

**What you'd get.** "The enrichment on 'gametocyte secreted candidates v3' could not run: it is a pasted set with no WDK step. 'WDK Strategy 214617320' holds the same 155 genes. Shall I run it on that instead?"
