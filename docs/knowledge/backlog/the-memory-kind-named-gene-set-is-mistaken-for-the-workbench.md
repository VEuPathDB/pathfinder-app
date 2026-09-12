---
type: Backlog
---

# The memory kind named gene_set is mistaken for the workbench

**What I did.** Through the web UI on plasmodb, the user asked to "save the 155 genes as a gene set called gametocyte secreted candidates".

**What I got.** The trace row `Remember: Remembered gametocyte secreted candidates as gene_set` (the `remember` tool with `kind="gene_set"`), no `create_workbench_gene_set` call, and the next tool used a gene-set id that does not exist. The workbench holds no new gene set.

**Why that's wrong.** The user's save produced a memory note, not a gene set; nothing in the workbench, nothing to run enrichment or EDA on, and the reply did not say so.

**Why it happens.** `domain/memory.py:7` names a memory kind `gene_set`, so the tool that stores a note about a gene set and the tool that creates one in the workbench (`ai/tools/standalone/workbench.py:43`) share the word; the model picked the memory tool.

**Fix.** The memory kind is renamed to what it is (a note about a gene set, e.g. `gene_set_note`) with a data migration for stored memories, or the `remember` tool's kind vocabulary states in its description that a gene set is created with `create_workbench_gene_set`; prefer the rename, since the host now declares its kinds (`AssistantSpec.memory_kinds`). Red first: a mock-scripted turn that saves a gene set must call the workbench tool.

**What you'd get.** "Save these genes as a gene set" creates a workbench gene set the next tools can read.
