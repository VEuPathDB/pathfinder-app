# Backlog

Everything known to be outstanding, ranked by what actually moves the product. Each item stands alone: a fresh session should be able to pick one up without this conversation.

Items are removed when done, not marked done. The [log](../log.md) records
what left.

## Ranked

1. [The web never sends an assistant id](the-web-cannot-reach-a-second-assistant.md) - two assistants are served and no front end can open a thread with the second one.
2. [Two data parts are outside PROTOCOL.md](two-runtime-data-parts-are-outside-the-protocol.md) - the runtime emits two kinds the protocol does not define and this app declares their schemas.
3. [Every turn reads strategy_revisions](every-turn-reads-the-strategy-revisions-table.md) - the turn driver makes PathFinder's strategy reads for every assistant, including the one that owns no strategy.
4. [A tier preset requires four phase roles](a-tier-preset-requires-four-phase-roles.md) - the tier control does not reach an assistant whose roles are not PathFinder's four.
5. [The pipeline and SSE instruments record nothing](the-pipeline-and-sse-instruments-record-nothing.md) - 19 OTEL instruments with no caller, so every dashboard series is empty.
6. [The WDK to AST conversion belongs to the tool server](wdk-conversion-belongs-to-the-tool-server.md) - 263 lines over library shapes only, so a second consumer must reimplement it.
7. [Assistant routing is the runtime's rule](assistant-routing-is-the-runtimes-rule.md) - resolving a turn's assistant and refusing a mismatch is kept in the app.
8. [The write-through store is generic machinery](the-write-through-store-is-generic-machinery.md) - a cache, a retrying upsert and a task spawner with no product in them.
9. [The drift gate names a file inside a package](the-drift-gate-names-a-file-inside-a-package.md) - the only import here that reaches past a published surface, for names that surface already publishes.

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [The test suite runs with input screening off](../decisions/the-test-suite-runs-with-input-screening-off.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
