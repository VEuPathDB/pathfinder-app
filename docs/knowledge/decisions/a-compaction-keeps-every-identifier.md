---
type: Decision
title: A compaction keeps every identifier of the notes it rewrites
description: The note compactor's output must carry every gene id, step id, strategy id, search name and count of three or more digits that its input notes carry, checked by an output validator; a rewrite that drops one is sent back naming what it dropped, and after two retries the compaction fails and the notes stay as they were. Trusting the instruction alone and a bigger model were rejected.
tags: [scratchpad, compaction, models, notes]
status: stable
---

# The choice

`ai/agents/compactor.py::build_compactor_agent` registers an output validator.
It reads the identifiers of the input notes and of the returned notes with
`domain/scratchpad_facts.py::hard_facts`, and raises `ModelRetry` when an input
identifier is absent from the output, listing at most 20 of them and a count of
the rest. The agent's `retries=2` gives three attempts. A third refusal ends the
run with `UnexpectedModelBehavior`; `assistant_core.scratchpad.compactor.compact_scratchpad`
lets it reach `ai/graph/nodes.py::_compact_the_notes`, which logs it, charges
the spend of all three attempts to the payer and leaves the notes uncompacted.
The instructions state the same invariant in one rule, so the model aims for it
on the first attempt.

The identifiers are read by shape, never from a list of words: locus tags
(`PF3D7_0102300`, `TGME49_233460`, `C4_01920W_A`), dotted gene ids
(`Tb927.10.1000`), four letters and six digits (`AAEL000001`), graph step ids
(`step_` and eight hex digits), WDK search url segments (`GenesBy...`,
`GenesWith...`) and standalone integers of three or more digits, which covers
WDK step and strategy ids and counts. A count loses its thousands separators.

# What was measured

Trigger-sized inputs of real unpinned notes (51 notes, 124 identifiers; 101
notes, 142 identifiers) on `openai:gpt-6-luna`, three runs each:

- Without the validator, the outputs kept 47 to 52% (51 notes) and 32 to 47%
  (101 notes) of the identifiers. Every gene id of one list was lost in every run.
- With the validator and the old instructions, 3 of 6 runs succeeded, each on
  its third attempt, at 110 to 175 s and about $0.009 a run. The first attempt
  kept 32 to 49% of the identifiers.
- With the validator and the invariant in the instructions, 11 of 12 runs
  succeeded: 4 on the first attempt, 4 on the second, 3 on the third. The first
  attempt kept 93 to 100%. A run took 59 to 295 s and cost $0.0035 to $0.016.
  The output bodies were 3,500 to 6,100 tokens, under the 10,000-token budget,
  so the runtime's budget trim removed no note.

# What was rejected

- **Trusting the instruction alone.** The instruction raises the first-attempt
  retention to 93 to 100%, but 8 of 12 first attempts still dropped one to
  ten identifiers. A compaction replaces the notes a later turn reads, so a
  dropped step id or gene id is lost without a trace.
- **A bigger model.** `gpt-5.6-luna` and the newer `gpt-6-luna` lost the same
  identifiers at trigger size (55% and 60% of all facts kept). The loss comes
  from a rewrite that summarizes, which a larger model also does. The validator
  checks the invariant after the model, whatever the model.
