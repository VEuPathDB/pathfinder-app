---
type: Backlog
---

# An enrichment request on a saved gene set has no tool that runs it

**What I did.** On plasmodb in the web app, a new conversation: "Compare my gene sets 'gametocyte secreted candidates' and 'gametocyte secreted candidates v3': how many genes overlap and which are only in one of them? Then run a GO enrichment on 'gametocyte secreted candidates' and summarize the top terms." Thread `3a63d386-a081-4d83-9419-2bbd9e51595e`.

**What I got.** The Lead listed the gene sets, read both sets' ids with `import_control_ids_from_gene_set` (155 and 155, identical), and replied "GO enrichment: I could not run the GO enrichment or retrieve its ranked terms in this session, so I won't invent a summary." No enrichment tool call appears in the turn; 5 trace rows, 104 s, $0.02.

**Why that's wrong.** Enrichment on a saved gene set is the workbench's stated purpose ("Save these genes as a gene set ... where enrichment, export, EDA and the control tools read it", the Lead's own instruction text), and the researcher asked for it in plain words. The honest refusal is the only good part.

**Why it happens.** `run_gene_set_enrichment` (the `geneset_enrichment` durable tool) is registered on the VERIFY sub-agent only (`ai/tools/toolsets/verification.py`), and there behind `verification_scope.warrants_enrichment()`, which offers it only on a turn whose build delta earns it. A turn that builds nothing never dispatches VERIFY, and the Lead carries no enrichment tool at all, so a request that names a saved gene set has no tool that can run it. The same shape kept the Lead from saving a gene set before the workbench save was added to it.

**Fix.** The Lead carries `run_gene_set_enrichment` for a saved gene set by id (the durable tool, `sequential=True`, through the same `inner_context` narrowing the workbench save uses), and `get_enrichment_results` to read the ranked terms when the task reports; the intent gate offers both on an unclassified turn and on a workbench request. VERIFY keeps its gated copy for a build's own result. Red first: a mock-scripted turn asking for GO enrichment on a named gene set reaches the durable tool through the Lead's toolset and parks on the task.

**What you'd get.** The request starts the enrichment task, the thread shows the task row, and the completion turn summarizes the ranked GO terms.
