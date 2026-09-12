---
type: Backlog
---

# A replaced subtree may restate a value the spec states

**What I did.** With the five-criterion toxodb spec loaded (criterion `step_780fd940`,
"Cell-cycle expression profile similar to MIC2 (TGME49_201780)", holding
`ProfileGeneId = TGME49_201780`), I sent two writes that change the same value.
First `update_leaf_params(step_780fd940, {"ProfileGeneId": "TGME49_300100"})`. Then, on a
fresh copy of the same strategy, `replace_subtree(step_780fd940, <a
GenesByToxoProfileSimilarity leaf with the same step id and
`ProfileGeneId = TGME49_300100`>)`.

**What I got.** The first write is refused: "VALIDATION_ERROR: nothing was applied and the
strategy is unchanged. The criterion 'Cell-cycle expression profile similar to MIC2
(TGME49_201780)' states the values this edit changes: ProfileGeneId states 'TGME49_201780'
and this edit sends 'TGME49_300100'." The second is applied: the step goes from `{}` to
`{'ProfileGeneId': 'TGME49_300100'}` and the write reaches VEuPathDB (one `create_step`,
three `create_combined_step`, four `delete_step`).

**Why that's wrong.** The strategy then runs a similarity search against RON2 under a
criterion whose words say MIC2. The count, the gene list and any export answer the second
gene, and the spec, the reply and the ledger all still say the first one. The two writes
change the same thing, so one refusing and the other applying is a route around the refusal.

**Why it happens.** `spec_edit_guard.value_contradiction` is called per operation, from
`update_leaf_params` and from the `updateStepParams` branch of `edit_contradiction`. A
`replaceSubtree` carries its leaves' parameters inside the tree it writes, and nothing reads
them. The operator half of the same guard does not have this gap: it runs on the tree the
batch leaves behind, in `commit.py::apply_operations_and_commit`.

**Fix.** Measure the values the same way the joins are measured. Carry the stated values on
`StrategyMutationContext` beside `stated_structure` (criterion id -> parameter -> wire value,
built by `AgentDeps.to_strategy_context()` from `spec_edit_guard.stated_values`), read the
contradicted pairs of the entry graph before the batch applies and of the result after, and
refuse a pair the batch introduces. Then drop the two per-operation call sites: one place,
every route. A value that already departed keeps its answer, the way a join does.

**What you'd get.** Both writes are refused with the same sentence, and the only way to change
a value the criterion's words carry is to restate the criterion in the framing pass.
