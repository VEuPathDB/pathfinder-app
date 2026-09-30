# Backlog

Everything known to be outstanding, ranked by what actually moves the product. Each item stands alone: a fresh session should be able to pick one up without this conversation.

Items are removed when done, not marked done. The [log](../log.md) records
what left.

## Ranked

1. [The Claude model is probed for images and documents](the-claude-models-are-probed-for-images-and-documents.md) - BLOCKED on keys: the OpenAI and Gemini keys answer; the probe runs on `claude-haiku-4-5` when the Anthropic account holds credit and the user says so.
2. [A curated search's data type is a catalog mark](a-curated-searchs-data-type-is-a-catalog-mark.md) - a data-type requirement grounds from an upload's type or an analysis's compute, but a curated search and a curated study still fall back to the search's name.
3. [A failed import tells the researcher to upload again](a-failed-import-tells-the-researcher-to-upload-again.md) - a `failed` VDI import is the site plugin's fault and installs on the next upload, but the dataset listing shows it as the plugin's message, like a refused file.
4. [A dataset search's organism is a catalog mark](a-dataset-searchs-organism-is-a-catalog-mark.md) - an expression dataset search publishes no organism parameter, so its INTERSECT with a search on another species is not refused and returns 0 by construction.
5. [A continuous comparator is refused before submit](a-continuous-comparator-is-refused-before-submit.md) - a label comparison on a continuous EDA variable passes the client's predicates and ends as a failed job with no reason.
6. [A generated strategy name is regenerated when an edit removes a criterion it names](a-generated-strategy-name-is-regenerated-when-an-edit-removes-a-criterion-it-names.md) - a thread's generated title stays on the strategy after the criterion it named is deleted; a marker on the strategy row and a turn-end check regenerate it, never a researcher's name.
7. [An export the graph editor added is named by the study](an-export-the-graph-editor-added-is-named-by-the-study.md) - an export stated from its document alone names its variables by id and shows no second count for its cut.
8. [A case compares the records two turns showed](a-case-compares-the-records-two-turns-showed.md) - no corpus field holds the same-sample rule; the runner keeps the last facts part only.
9. [Each corpus case runs as a fresh user](each-corpus-case-runs-as-a-fresh-user.md) - every case runs as the debugger's one user, so earlier runs' gene sets, memories and cases are read by later ones; the user id needs a seam in `devtools/chat.py`.
10. [The vocabulary caps live beside the rule that reads them](the-vocabulary-caps-live-beside-the-rule-that-reads-them.md) - `veupathdb-mcp` a35 imports the two vocabulary caps as private names from another module; one module owns the caps and the cut in the next tag.

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [One injection judge, and what a failed judgement means](../decisions/one-injection-judge-and-what-a-failed-judgement-means.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
