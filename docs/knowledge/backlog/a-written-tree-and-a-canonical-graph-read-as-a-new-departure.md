---
type: Backlog
---

# A written tree and a canonical graph read as a new departure

**What I did.** With the five-criterion toxodb spec loaded (criterion `step_780fd940`,
"Cell-cycle expression profile similar to MIC2 (TGME49_201780)"), I put the graph in the
state a push leaves behind: `step_780fd940` holding the case-folded gene id
`tgme49_300100`, the form the catalog answers with. Then I called `build_strategy` twice
with the same tree and the same logical value for that leaf, in the two wire forms the
value has: `tgme49_300100` and `TGME49_300100`.

**What I got.**

```
leaf sends 'tgme49_300100'  -> the guard passes it and the build reaches the push
leaf sends 'TGME49_300100'  -> REJECTED: the criterion 'Cell-cycle expression profile
  similar to MIC2 (TGME49_201780)' states ProfileGeneId = 'TGME49_201780', and this write
  sends 'TGME49_300100', so the strategy would answer a different question. A value the
  spec states changes in the spec first (set_criterion, in the framing pass).
```

Same graph, same operation, same logical value, opposite verdicts.

**Why that's wrong.** The value the leaf carries already departed from the spec before the
turn began, and the rule is that a departed value keeps its answer until something
restates the criterion. The build is refused for a departure it did not introduce, the
message names a parameter the caller did not change, and the whole tree is lost. Which of
the two answers the researcher gets depends on the wire form the model happens to write.

**Why it happens.** The guard compares the value the graph holds at entry with the value
the batch leaves behind. `services/strategies/step_wdk_push.py::_validate_plan_params`
assigns `step.parameters = validated.params` on the live steps, so every push leaves the
graph in the catalog's form, while a tree the model writes is in the model's form.
`update_leaf_params` and `replace_subtree` state both sides in the catalog's form
(`ai/tools/standalone/_spec_edit_checks.py::canonical_sides`, carried on
`StrategyMutationContext.entry_values`); the other four paths into the guard do not, and
read the graph as it stands: `build_strategy`
(`services/strategies/spec_build.py::_a_build_the_spec_refuses`), `apply_operations`
(`ai/tools/standalone/strategy.py`), the Lead's spec edits
(`ai/lead/edit_dispatch.py::_push_the_edit`) and `eda_step`
(`ai/tools/standalone/eda_step.py`).

**Fix.** Give the remaining paths the same two sides the patched ones have. Each writes
whole steps, so each can canonicalize the leaves the spec states values for
(`canonicalize_stated_leaves`) and hand `canonical_sides` the steps it writes, exactly as
`replace_subtree` does; `spec_build.py` already reads `deps.entry_values` and needs the
tool to fill it. A shared seam is worth measuring first: the canonicalization belongs to
whoever writes a step, and five callers writing it by hand is four chances to forget.

**What you'd get.** Both forms of the same departed value applied on every path, and a
genuine change of a stated value refused on every path.
