# Backlog

Everything known to be outstanding, ranked by what actually moves the product. Each item stands alone: a fresh session should be able to pick one up without this conversation.

Items are removed when done, not marked done. The [log](../log.md) records
what left.

## Ranked

1. [The Claude model is probed for images and documents](the-claude-models-are-probed-for-images-and-documents.md) - BLOCKED on keys: the OpenAI and Gemini keys answer; the probe runs on `claude-haiku-4-5` when the Anthropic account holds credit and the user says so.
2. [A curated search's data type is a catalog mark](a-curated-searchs-data-type-is-a-catalog-mark.md) - a data-type requirement grounds from an upload's type or an analysis's compute, but a curated search and a curated study still fall back to the search's name.
4. [A dataset search's organism is a catalog mark](a-dataset-searchs-organism-is-a-catalog-mark.md) - an expression dataset search publishes no organism parameter, so its INTERSECT with a search on another species is not refused and returns 0 by construction.
12. [A dependent pick's label is the vocabulary it was bound under](a-dependent-picks-label-is-the-vocabulary-it-was-bound-under.md) - a value the spec holds keeps its bound label; a value first read from a site-edited step is still labelled on the published sheet, so a dependent pick only its bound parents list shows none.

15. [A membership question is answered by a read-only search](a-membership-question-is-answered-by-a-read-only-search.md) - "which sampled genes also have a signal peptide" is answered from record pages over other genes; a read-only ids search answers it.
19. [A card holds one change per stated part](a-card-holds-one-change-per-stated-part.md) - DESIGN: a second card answer under one message never reaches the classifier, and a proposed change names no stated part; the card is held to the stated parts once each change names the constraint keys it answers.
21. [A count question about a catalog search is answered read-only](a-count-question-about-a-catalog-search-is-answered-read-only.md) - four guessed search names refused, the reply claims the search is absent; a read-only catalog count.
29. [A decision model is chosen on our own scorecards](a-decision-model-is-chosen-on-our-own-scorecards.md) - PARKED: Cloudflare's open-weight Clef and Clef-flash take Jev's request shape; the five Jev scorecards are rerun on both, on hosted Workers AI, before any decision model is wired.

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [One injection judge, and what a failed judgement means](../decisions/one-injection-judge-and-what-a-failed-judgement-means.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
