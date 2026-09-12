# Backlog

Everything known to be outstanding, ranked by what actually moves the product. Each item stands alone: a fresh session should be able to pick one up without this conversation.

Items are removed when done, not marked done. The [log](../log.md) records
what left.

## Ranked

1. [A completion turn runs with no WDK login](a-durable-tool-started-by-a-completion-turn-has-no-wdk-login.md) - the completion turn opens outside the carried job context, so every WDK-backed tool in it, durable or not, is refused for a login the researcher has (measured on two sites).
2. [A step the editor deleted cannot be added back by the assistant](a-step-the-editor-deleted-cannot-be-added-back-by-the-assistant.md) - the turn starts from the checkpoint's framed spec, never reconciled with the graph the editor changed, so the re-added criterion diffs as kept and nothing is pushed.
3. [A transform named in an AND statement can meet at no combine](a-transform-named-in-an-and-statement-can-meet-at-no-combine.md) - the combination check matches a statement's terms to the transform criterion and then wants it as a member of a combine, so a transform-then-filter request is refused until FRAME runs out of retries.
4. [An EDA export is impossible on the turn after the preview](an-eda-export-is-impossible-on-the-turn-after-the-preview.md) - the export tool is gated on a per-message preview marker, so the turn that takes the assistant's own offer cannot export and is told to run the compute again.
5. [A sub-agent that runs out of tool retries ends the turn with a canned line](a-sub-agent-that-runs-out-of-tool-retries-ends-the-turn-with-a-canned-line.md) - pydantic-ai's retries-exceeded error is caught nowhere, so the Lead's run unwinds and the thread gets 'rephrase' instead of the refusal.
6. [A step keeps the name of the parameters it no longer has](a-step-keeps-the-name-of-the-parameters-it-no-longer-has.md) - an editor parameter change writes the values and not the name, so the graph and the researcher's VEuPathDB account state a criterion the step no longer applies.
7. [Consult answers can be dropped between the carousel and the turn](consult-answers-can-be-dropped-between-the-carousel-and-the-turn.md) - the answers ride a message-list state update written in the same tick as the approval response, so a turn can resume with none and ask again.
8. [A stored preference is not applied to the next request](a-stored-preference-is-not-applied-to-the-next-request.md) - turn-entry retrieval is top-8 by similarity across every kind, so a default-organism preference never reaches a request about signal peptides and the assistant asks the question the preference answers.
9. [A second preference of the same name does not replace the first](a-second-preference-of-the-same-name-does-not-replace-the-first.md) - every remember mints a new key, so a changed standing preference accumulates beside the old one and a turn silently picks one.
10. [The memories a turn recalls never reach the thread](the-memories-a-turn-recalls-never-reach-the-thread.md) - the lead node writes the recalled-memories chunk bare instead of in the writer envelope, so the runner drops it and no thread has ever shown one.
11. [An enrichment or an export of a saved gene set has no tool that runs it](an-enrichment-request-on-a-saved-gene-set-has-no-tool.md) - the enrichment durable tool and both export tools are VERIFY-only, so a workbench request to enrich or download a named set is honestly refused.
12. [A study that is not in the catalog is searched for thirty-seven times](a-study-that-is-not-in-the-catalog-is-searched-for-thirty-seven-times.md) - the study search reports a semantic top-k as a match and nothing caps one discovery tool per turn, so an absent study costs a dollar and twelve minutes before the honest answer.
13. [Site help cannot name a site's organisms](site-help-cannot-name-a-sites-organisms.md) - describe_site carries no organism vocabulary, so the site's help assistant honestly refuses the first question a researcher asks.
14. [The debugger hangs when a turn calls a durable tool](the-debugger-hangs-when-a-turn-calls-a-durable-tool.md) - a durable call raises AppNotOpen in the in-process debugger and the run neither fails nor completes, so no artifacts are written.
15. [The worker reaches into private tool modules](the-worker-reaches-into-private-tool-modules.md) - two job bodies import private modules of the tool package, the same shape the Lead guard now forbids under ai/lead and ai/graph.
16. [The revert dialog says the strategy graph is kept](the-revert-dialog-says-the-strategy-graph-is-kept.md) - the copy promises the graph survives; the service restores the snapshot as a new WDK strategy.
17. [A written tree and a canonical graph read as a new departure](a-written-tree-and-a-canonical-graph-read-as-a-new-departure.md) - four write paths still compare the model's wire form against the catalog's, so a canonicalizer can turn an untouched value into a refusal.

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [The test suite runs with input screening off](../decisions/the-test-suite-runs-with-input-screening-off.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
