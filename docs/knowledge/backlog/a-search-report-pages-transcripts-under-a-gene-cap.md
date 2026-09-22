---
type: Backlog
---

# A search report pages transcripts under a gene cap

`services/experiment/variant_comparison.py::run_variant_search` reads an anonymous
search report (`client.run_search_report`) with a 50,000-row cap. On a transcript
search the rows are transcripts while the total counts genes, so a search close to
the cap can be flagged `truncated` while it holds fewer genes than rows. The ids
themselves stay right: the first id part is the gene id and the ids go into a set.

## Fix

`veupathdb-py` gives `run_search_report` a `view_filters` keyword, sent as the
top-level `viewFilters` of the report body (WDK-FILTER-003), the way
`get_step_answer` takes one since v0.1.0a13. `run_variant_search` then passes
`view_filters_for(spec.record_type)` from `veupathdb_mcp.wdk`, and the step
pagers and the search pager follow one rule. Needs a client release and a pin.
