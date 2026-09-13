# Backlog

Everything known to be outstanding, ranked by what actually moves the product. Each item stands alone: a fresh session should be able to pick one up without this conversation.

Items are removed when done, not marked done. The [log](../log.md) records
what left.

## Ranked

1. [A saved gene set records the step id the model typed](a-saved-gene-set-records-the-step-id-the-model-typed.md) - the save tool writes the WDK ids the model passes instead of reading them from the sync state, so a strategy-backed set can point at a step that does not exist.
2. [A refused analysis is answered with another gene set](a-refused-analysis-is-answered-with-another-gene-set.md) - a failed enrichment task was routed around by trying a neighbouring set, and the reply named the researcher's set for another set's terms.
3. [Enrichment from chat cannot read a pasted gene set](enrichment-from-chat-cannot-read-a-pasted-gene-set.md) - the durable path skips the temporary-dataset step the HTTP route builds, so a set that enriches in the workbench fails from chat.
4. [A transform named in an AND statement can meet at no combine](a-transform-named-in-an-and-statement-can-meet-at-no-combine.md) - the combination check matches a statement's terms to the transform criterion and then wants it as a member of a combine, so a transform-then-filter request is refused until FRAME runs out of retries.
5. [An EDA export is impossible on the turn after the preview](an-eda-export-is-impossible-on-the-turn-after-the-preview.md) - the export tool is gated on a per-message preview marker, so the turn that takes the assistant's own offer cannot export and is told to run the compute again.
6. [A sub-agent that runs out of tool retries ends the turn with a canned line](a-sub-agent-that-runs-out-of-tool-retries-ends-the-turn-with-a-canned-line.md) - pydantic-ai's retries-exceeded error is caught nowhere, so the Lead's run unwinds and the thread gets 'rephrase' instead of the refusal.
7. [A step keeps the name of the parameters it no longer has](a-step-keeps-the-name-of-the-parameters-it-no-longer-has.md) - an editor parameter change writes the values and not the name, so the graph and the researcher's VEuPathDB account state a criterion the step no longer applies.
8. [A dispatch and the Lead's own durable call cannot both be parked](a-dispatch-and-the-leads-own-durable-call-cannot-both-be-parked.md) - the resume hands every parked call to the sub-agent, so a turn that fires both is refused; the split is one app-side function.
9. [A second preference of the same name does not replace the first](a-second-preference-of-the-same-name-does-not-replace-the-first.md) - every remember mints a new key, so a changed standing preference accumulates beside the old one and a turn silently picks one.
10. [Site help cannot name a site's organisms](site-help-cannot-name-a-sites-organisms.md) - describe_site carries no organism vocabulary, so the site's help assistant honestly refuses the first question a researcher asks.
11. [The debugger hangs when a turn calls a durable tool](the-debugger-hangs-when-a-turn-calls-a-durable-tool.md) - a durable call raises AppNotOpen in the in-process debugger and the run neither fails nor completes, so no artifacts are written.
12. [A written tree and a canonical graph read as a new departure](a-written-tree-and-a-canonical-graph-read-as-a-new-departure.md) - four write paths still compare the model's wire form against the catalog's, so a canonicalizer can turn an untouched value into a refusal.
13. [The draft spec prunes a departed step its own way](the-draft-spec-prunes-a-departed-step-its-own-way.md) - a second, weaker pruning in the agent state drops a criterion and leaves the structure behind, where the domain reconciliation keeps the two in step.

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [The test suite runs with input screening off](../decisions/the-test-suite-runs-with-input-screening-off.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
