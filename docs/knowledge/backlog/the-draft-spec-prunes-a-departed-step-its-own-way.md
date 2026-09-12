---
type: Backlog
---

# The draft spec prunes a departed step its own way

**What I did.** Built a draft spec with two criteria, the seed leaf
`step_3fa0e628` (GenesBySignalPeptide) and the transform `orthologs`
(GenesByOrthologs) over it, set it as `AgentToolState.operational_spec_draft`,
and called `drop_criteria_for_steps({"orthologs"})`
(`apps/api/src/pathfinder/ai/agents/state.py:174`), which is what a turn calls
when the graph loses that step.

**What I got.**

```
criteria: ['step_3fa0e628']
structure: None
```

The same input through the domain function that now owns this invariant,
`domain/strategy/spec_reconciliation.py::spec_reconciled_with_graph`, gives
`criteria: ['step_3fa0e628']` and `structure: leaf step_3fa0e628`
(`tests/unit/domain/strategy/test_spec_reconciliation.py::test_a_transform_whose_step_left_collapses_to_its_input`).

**Why that's wrong.** The seed step is still in the graph and its criterion is
still in the spec, and the spec now states no structure at all. The next edit
reads a spec with a criterion the structure does not name, so
`fold_option_criteria` treats the seed as an option to fold onto another
criterion's search, and `operations_for` refuses the edit because the spec
states no structure. The researcher loses the turn on a step nobody deleted.
The reverse case costs the same: a combine that keeps one input stays a combine
with one input, and a criterion the pruning orphans is never removed from
`spec.criteria`.

**Why it happens.** `ai/agents/state.py::_structure_without` (`:249`) returns
`None` for any node whose criterion departed, so the node's whole input subtree
goes with it, and `drop_criteria_for_steps` removes only the criteria it was
handed, never the ones the pruning orphaned. It is a second implementation of
the invariant `domain/strategy/spec_reconciliation.py` now states, in `ai/`
instead of `domain/`, and weaker.

**Fix.** Give `spec_reconciled_with_graph` a form that takes the live step ids
instead of a `StrategyGraph`, have `drop_criteria_for_steps` call it, and delete
`ai/agents/state.py::_structure_without`. One implementation of the invariant,
in the layer that owns the spec.

**What you'd get.** Dropping the transform leaves `criteria: ['step_3fa0e628']`
and `structure: leaf step_3fa0e628`, so the next edit reads a spec whose
criteria and structure name the same steps the graph holds.
