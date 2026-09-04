---
type: Decision
title: The strategy structure is a tree, because its shape is the science
description: FRAME's set_structure took a flat list and left-folded it, so a UNION branch on the secondary input was inexpressible - and that changes the answer.
tags: [agents, frame, wdk-alignment, strategy-graph]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# How it surfaced

Given a multi-criterion request, the Lead framed all 8 criteria and then **refused to build**, saying:

> "The current WDK assembly cannot encode those parenthesized branches exactly in one left-fold strategy, so I need to preserve that topology rather than silently flatten it."

It was right, and it was right to refuse. That is the no-silent-degradation principle working: a wrong answer delivered confidently is worse than a question.

# The defect

`set_structure(criterion_ids, operators)` left-folded a flat list:

```python
root = nodes[0]
for node in nodes[1:]:
    root = StructureNode(kind="combine", operator=op, inputs=[root, node])
```

That can only produce a left spine. Meanwhile:

- `StructureNode` already carried `inputs: list[StructureNode]` -- a general tree;
- `build_step_tree` already recursed on **both** primary and secondary inputs;
- WDK step trees carry a primary **and** a secondary input, which `CLAUDE.md` lists as non-negotiable.

So the domain, the seam and WDK could all express a nested branch. Only the tool could not. FRAME's own instruction even told the model to "UNION them into one branch first, then INTERSECT that branch with the others" -- asking for a shape its tool could not encode.

# Why the shape is not cosmetic

`A INTERSECT (B UNION C)` is not `(A INTERSECT B) UNION C`. The first asks "kinases with a signal peptide, where kinase evidence may come from either source". The second asks something no researcher wants.

Measured on live WDK after the fix:

| set | genes |
|---|---|
| InterPro PF00069 | 87 |
| GO:0016301 | 128 |
| **union branch** | **134** |
| signal peptide | 603 |
| **final intersection** | **3** |

The union of 87 and 128 giving 134 is only possible if the two kinase sets were combined **first** and then intersected. The same question under the old flattened shape returned **2** genes; the third, PyKII (PF3D7_1037100), is reachable only through GO:0016301. The fix did not just change a topology, it recovered a gene.

# The change

`set_structure(root: StructureNode)` -- a recursive model, which schematizes for the tool as `$defs` with a self-reference (the same pattern `apply_operations` already proved). The FRAME instruction now shows the three node shapes and says explicitly not to flatten.

# Anchor

`set_structure` in `ai/tools/standalone/frame_spec.py`. Guarded by `TestNestedBranches` in `tests/unit/ai/tools/test_frame_structure.py` and `TestNestedBranchesReachWdk` in `tests/unit/domain/strategy/test_operational_spec.py`, which pins that the branch survives all the way to the WDK step tree.
