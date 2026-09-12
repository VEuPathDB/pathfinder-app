# Backlog

Everything known to be outstanding, ranked by what actually moves the product. Each item stands alone: a fresh session should be able to pick one up without this conversation.

Items are removed when done, not marked done. The [log](../log.md) records
what left.

## Ranked

1. [A prior turn's requirements are dropped when the next turn answers a question](a-prior-turns-requirements-are-dropped-when-the-next-turn-answers-a-question.md) - the protease requirement vanished after a narrowing exchange and the reply never said so; recommended defaults are not carried either.
2. [A draft thread fetches a conversation that does not exist yet](a-draft-thread-fetches-a-conversation-that-does-not-exist-yet.md) - two 404s and two console errors on every new chat.
3. [An unknown count is sent to the thread as zero](an-unknown-count-is-sent-as-zero.md) - the graph snapshot and the strategy metadata carry `int`, so a count nobody measured is drawn in the thread as 0 genes.
4. [A thread reopened during its turn shows nothing until a later reload](a-thread-reopened-during-its-turn-shows-nothing-until-a-reload.md) - a fresh tab on a running turn gets a snapshot that ends at the prompt with no open message, so it never opens the tail.
5. [A zero result is recovered by loosening the spec](a-zero-result-is-recovered-by-loosening-the-spec.md) - a realized zero is dispatched to BUILD as a recovery, and BUILD flips a filter to a union and widens a parameter nobody asked for; the edit tools never compare an operator or a stated value with the spec.
6. [The EDA filter sheet is lost to the history elision](the-eda-filter-sheet-is-lost-to-the-history-elision.md) - the second sheet for a study sends 0 of its 55 vocabulary values, and the first one was cut to 294 characters four calls earlier.
7. [No turn records the gene sets it created](no-turn-records-the-gene-sets-it-created.md) - `created_gene_set_ids` has no production writer, so the gene-set-note auto-write has never fired.
8. [Only one agent answers a refusal, and no sub-agent keeps a defect loud](only-one-agent-answers-a-refusal-and-none-keeps-a-defect-loud.md) - the refusal seam is the Lead's alone; the three sub-agents route a defect into a directive.

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [The test suite runs with input screening off](../decisions/the-test-suite-runs-with-input-screening-off.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
