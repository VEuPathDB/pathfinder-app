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
11. [A search report sends a tree value as its leaves](a-search-report-sends-a-tree-value-as-its-leaves.md) - `veupathdb-py` expands a tree parent to its leaves for a step and not for an anonymous report, and its retry error prints an empty timeout message; PathFinder expands and names the error class itself until the release that fixes both.
12. [A dependent pick's label is the vocabulary it was bound under](a-dependent-picks-label-is-the-vocabulary-it-was-bound-under.md) - the bind labels a dependent pick under its bound parents and hydration and replay under the published vocabulary; a plasmodb `GenesByInterproDomain.domain_typeahead` recording under two organisms measures it.

15. [A membership question is answered by a read-only search](a-membership-question-is-answered-by-a-read-only-search.md) - "which sampled genes also have a signal peptide" is answered from record pages over other genes; a read-only ids search answers it.
16. [An unquoted reading is labelled as separate words](an-unquoted-reading-is-labelled-as-separate-words.md) - the word reading of a quoted term is labelled the phrase, and a reading is built from the sentence; alternatives derive from the bound term only.
17. [A quoted value and an initial value carry their source](a-quoted-value-and-an-initial-value-carry-their-source.md) - `"GPI anchored" (chosen)` for a quoted message value and `Start at: 1 (chosen)` at the published initial value.
18. [The retired row names the dropped criterion's requirement](the-retired-row-names-the-dropped-criterions-requirement.md) - a MINUS arm's delete prints `'kinase AND no TM' is withdrawn` while the kinase step runs.
19. [A card holds one change per stated part](a-card-holds-one-change-per-stated-part.md) - a two-arm request gets a one-change card called focused; the card is held to the classifier's asks and unique genes show products.
21. [A count question about a catalog search is answered read-only](a-count-question-about-a-catalog-search-is-answered-read-only.md) - four guessed search names refused, the reply claims the search is absent; a read-only catalog count.
24. [A genus the message names is stated on its species](a-genus-the-message-names-is-stated-on-its-species.md) - "Cryptosporidium" binds as 30 chosen species with a stale took-0-of-0 row; the parent the message names is stated.
27. [A carry to orthologs is one transform](a-carry-to-orthologs-is-one-transform.md) - "carry these to their orthologs in X" is built as a round trip that keeps the source organism; the words choose the shape.
28. [A lookup ranks the request's own words first](a-lookup-ranks-the-requests-own-words-first.md) - a capped lookup list hides the entries that carry the request's words behind the pass's synonyms; the library's `read_options` ranks them first.
29. [A decision model is chosen on our own scorecards](a-decision-model-is-chosen-on-our-own-scorecards.md) - PARKED: Cloudflare's open-weight Clef and Clef-flash take Jev's request shape; the five Jev scorecards are rerun on both, on hosted Workers AI, before any decision model is wired.

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [One injection judge, and what a failed judgement means](../decisions/one-injection-judge-and-what-a-failed-judgement-means.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
