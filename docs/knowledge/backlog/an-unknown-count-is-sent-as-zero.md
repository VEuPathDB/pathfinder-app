---
type: Backlog
---

# An unknown count is sent to the thread as zero

**What I did.** Built a one-step strategy on plasmodb whose step (`step_a1b2c3d4`, WDK step 440432473, `GenesByMicroarrayBirkholtz`) VEuPathDB refused: the session holds `step_counts = {step_a1b2c3d4: None}` and `wdk_push_errors = {step_a1b2c3d4: "422 profileset_generic: Invalid value"}`. Then built the two data parts a turn emits for that graph.

**What I got.** `data-graph-snapshot` -> `{"strategyId": "g1", "geneCount": 0, "nodes": [{"id": "step_a1b2c3d4", "searchName": "GenesByMicroarrayBirkholtz", "estimatedSize": 0}], "edges": []}` and `data-strategy-meta` -> `{"strategyId": "g1", "name": "Kinases", "isSaved": false, "estimatedSize": 0, "recordClassName": "transcript"}`. The thread draws "1 step, 0 genes" (`DataGraphSnapshot.tsx`) and "Kinases - 0 genes" (`DataStrategyMeta.tsx`).

**Why that's wrong.** Zero is a result: it says the search ran and matched nothing. The user reads a figure in the transcript saying their strategy returns no genes, when the truth is that no count was ever measured. Every other count surface says "count not available" for the same step.

**Why it happens.** `GraphNode.estimated_size`, `GraphSnapshot.gene_count` and `StrategyMeta.estimated_size` are `int = Field(ge=0)` (`ai/stream_part_payloads.py`), so `_count_for_step` and `strategy_meta_chunk` (`ai/tools/standalone/_stream_parts.py`) coerce an unknown count to 0 to satisfy the type.

**Fix.** Widen the three fields to `int | None`, the shape `StepResponse.estimatedSize` already has, and read them through `citable_count` (`domain/strategy/build_outcome.py`) like every other count surface. Regenerate the spec and the Kubb output, and make the two renderers draw an unknown count as "count not available" rather than a number.

**What you'd get.** A refused or unmeasured step reports no number in the thread, and a real zero keeps meaning "the search matched nothing".
