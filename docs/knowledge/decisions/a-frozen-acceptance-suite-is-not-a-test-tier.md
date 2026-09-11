---
type: Decision
title: A frozen acceptance suite is not a test tier, so the EDA and thread suites were folded into the live ones
description: The four acceptance suites that no script, hook or CI job collected are deleted, and the contracts only they pinned were moved into the live tests beside their code. Wiring them into a nightly workflow was rejected, because a suite whose only reader is a closed program's verifier pins its plan rather than its code.
tags: [testing, conventions, eda, thread, ci]
generated: { by: claude-code/opus-5, at: 2026-09-03T00:00:00Z }
status: stable
---

# What was decided

The EDA and thread programs each shipped a frozen, behavior-only acceptance
suite under a no-edit rule: the tests were written before the code, from the
program's plan, and a batch closed only when its module passed unmodified.
Both programs are finished, and the four suites are deleted:

- `apps/web/src/acceptance/**` and `apps/web/vitest.acceptance.config.ts`
- the assistant client's `packages/assistant-client-ts/tests/acceptance/**`, its acceptance vitest
  config and its `test:acceptance` script
- `apps/web/e2e/acceptance/**` and the `eda-acceptance` / `thread-acceptance`
  playwright projects
- `apps/api/src/pathfinder/tests/acceptance/**`, the `eda_acceptance` marker
  and the `addopts = "-m 'not eda_acceptance'"` line that deselected it

Four contracts were pinned only there and now live beside their code:
`retained_point_ids` is monotone in the effect size and its two directions
partition the retained set
(`tests/unit/services/eda/test_volcano_thresholds.py`); the same two
properties of `selectVolcanoGenes` (`src/lib/eda/volcanoSelection.test.ts`);
a `data-turn-status` part does not close a trace run
(`tests/conformance/trace.test.ts`); and a completion turn re-runs nothing the
parked model step already settled
(`tests/unit/ai/lead/test_sub_agent_stream_durable.py`). The recorded turn the
suites read is now `apps/web/src/features/conversation/__fixtures__/recordedTurn.json`,
which two live tests already imported.

# What was rejected

**Wiring the suites into a nightly workflow.** It would make them run, but not
useful. Every module opened with a guarded import and a
`describe.skipIf(module === null)` or a `pytest.importorskip`, so a suite whose
target was deleted reported green rather than red - the exact failure a test
exists to produce. The no-edit rule that made them valuable during a batch is
what makes them wrong afterwards: a frozen test pins the plan that wrote it, so
it cannot follow the code it guards, and the next change to that code has to
either edit a file the rule forbids editing or delete it. Nineteen files that
no gate collected also cost every reader a second, contradictory source for the
same contract.

**Keeping them read-only as documentation.** The bundle's own rule refuses a
doc that restates the code; a test tree that restates the live tests is the
same rot with a longer runtime.

# What would prove this wrong

A contract that regressed with every gate green, and whose only assertion had
been in one of the deleted files. The four ported properties above are the
list of contracts that were at risk; each has an assertion in a file that
`yarn test`, `uv run pytest` or the client package's `yarn test` collects.
