# Backlog

Everything known to be outstanding, ranked by what actually moves the product. Each item stands alone: a fresh session should be able to pick one up without this conversation.

Items are removed when done, not marked done. The [log](../log.md) records
what left.

## Ranked

1. [An EDA analysis is a criterion of the spec](an-eda-analysis-is-a-criterion-of-the-spec.md) - an exported EDA step's criterion carries no meaning FRAME can read and the handoff is keyed on the dataset, so a re-frame drops the step and fills a second comparison with a fold-change search.
2. [A search report pages transcripts under a gene cap](a-search-report-pages-transcripts-under-a-gene-cap.md) - `run_search_report` takes no view filter, so `variant_comparison` can flag a transcript search truncated early.

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [One injection judge, and what a failed judgement means](../decisions/one-injection-judge-and-what-a-failed-judgement-means.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
