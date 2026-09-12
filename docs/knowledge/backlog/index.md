# Backlog

Everything known to be outstanding, ranked by what actually moves the product. Each item stands alone: a fresh session should be able to pick one up without this conversation.

Items are removed when done, not marked done. The [log](../log.md) records
what left.

## Ranked

1. [A killed durable worker leaves its task running for good](a-killed-durable-worker-leaves-its-task-running-for-good.md) - the stalled-job sweep closes a chat turn's stream and never a durable call's, so the task row stays `running`, the thread keeps streaming, and the rail shows work that ended.
2. [The Lead reaches into private tool modules](the-lead-reaches-into-private-tool-modules.md) - six imports across four Lead modules name a leading-underscore module under the standalone tools, a surface nothing declares.
3. [A departed value and a canonicalizer read as a new departure](a-departed-value-and-a-canonicalizer-read-as-a-new-departure.md) - a stated value that already departed in the graph, rewritten by the catalog's canonicalizer, refuses a patch that touched nothing stated.

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [The test suite runs with input screening off](../decisions/the-test-suite-runs-with-input-screening-off.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
