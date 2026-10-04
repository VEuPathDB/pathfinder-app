# Backlog

Everything known to be outstanding, ranked by what actually moves the product. Each item stands alone: a fresh session should be able to pick one up without this conversation.

Items are removed when done, not marked done. The [log](../log.md) records
what left.

## Ranked

1. [The Claude model is probed for images and documents](the-claude-models-are-probed-for-images-and-documents.md) - BLOCKED on keys: the OpenAI and Gemini keys answer; the probe runs on `claude-haiku-4-5` when the Anthropic account holds credit and the user says so.
12. [A dependent pick's label is the vocabulary it was bound under](a-dependent-picks-label-is-the-vocabulary-it-was-bound-under.md) - a dependent pick is labelled under its own parents on the bind, on hydration and on replay; the site-default count still reads a dependent pick at the published default, and no recorded dependent pick has a non-empty published default yet.

21. [A count question about a catalog search is answered read-only](a-count-question-about-a-catalog-search-is-answered-read-only.md) - the read-only count and membership tools are done; a reply can still claim a search is absent without a lookup of the turn, because the sub-agent's catalog lookups are not on the turn record the reply check reads; a membership that holds no gene can still state a shared count of 0 after saying none.
30. [The same sample again is the sample the thread showed](the-same-sample-again-is-the-sample-shown.md) - a repeat of an earlier sample is read afresh from the step's ids; two of five genes differ.
31. [A study-backed search carries its organism scope](a-study-backed-search-carries-its-organism-scope.md) - an EDA study search has no organism scope, so a cross-strain intersect builds and returns 0.
32. [The corpus scorer reads a combine without operand order](the-corpus-scorer-reads-a-combine-without-operand-order.md) - an INTERSECT with its inputs swapped fails its case, and a same-records check counts the records a check read.
33. [A reply never repeats a refusal it corrected](a-reply-never-repeats-a-refusal-it-corrected.md) - a reply can narrate a card the turn refused and replaced.
29. [A decision model is chosen on our own scorecards](a-decision-model-is-chosen-on-our-own-scorecards.md) - PARKED: Cloudflare's open-weight Clef and Clef-flash take Jev's request shape; the five Jev scorecards are rerun on both, on hosted Workers AI, before any decision model is wired.

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [One injection judge, and what a failed judgement means](../decisions/one-injection-judge-and-what-a-failed-judgement-means.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
