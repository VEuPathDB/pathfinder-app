---
type: Decision
title: A filter clause is bound by its facet
description: A filter statement names a facet by its exact term or display, and the facet decides the clause's type and isRange; a range is read from the term summary only for a bound range clause, under the other clauses, and a range or a minSelectedCount the value misses is refused as wdk-client refuses it. The filter shorthand and a whole-sheet range read were rejected.
tags: [parameters, filters, wdk-alignment, frame]
generated: { by: claude-code/opus-5.5, at: 2026-11-21T00:00:00Z }
status: stable
---

# What was decided

A model states a filter value as a list of `{field, value, includeUnknown}`
objects (`FilterProposal`). `field` names one facet of the parameter's ontology
by its exact term or its exact display (`FilterFacets.find`); a substring, a
case change or a near spelling names nothing. The parameter's schema lists
every term and display as the values `field` takes. The facet decides the clause:
its `type` and `isRange` come from the ontology term, never from the
statement (`FilterFacet.clause`). A range facet takes `{"min": .., "max": ..}`
with either bound left out, and a member facet takes a list of its members. A
member the facet does not hold is refused with the members it holds. A facet
with no member under the current parent values is refused. An empty list is
refused.

`FilterValue` holds the strict clause union WDK's `FilterParamNewStableValue`
parses: `StringMembers`, `NumberMembers`, `NumberRange`, `DateRange` and
`MultiMembers`. No field has a default, so every clause carries `field`,
`type`, `isRange`, `includeUnknown` and `value`, and a clause that lacks one
does not parse (WDK-PARAM-018). The value with no clauses is `{"filters": []}`,
WDK's own `initialDisplayValue`; it is not WDK's empty value, which is `""` and
exists only where the parameter allows it (WDK-PARAM-019). The web parses and writes filter values with the
generated clause types (`filterValueSchema`) and keeps no copy of its own.

A held value is bound again through the same facets (`FilterFacets.held`), so a
card option and a variant read use the bind and no second checker.

# A range is read only for a bound range clause, under the other clauses

WDK's values map leaves out every `isRange` term, so a range facet's bounds
come only from `POST .../{param}/ontology-term-summary`. The range is read the
way wdk-client reads it: the minimum and the maximum of the `valueCounts` whose
`filteredCount` is above zero, with the value's other clauses sent as
`filters` and every parent as `contextParamValues` (`FacetRange.of`). The other
clauses change the range: on qa.plasmodb.org `total_variants` spans 1 to 4,823
variants over 5,643 records alone, and 2 to 4,823 over 3,207 records under a
`most_severe_impact` clause of `HIGH`.

The range is read once for each range clause a statement binds, and an options
read reads up to three facets its query ranks first (`with_ranges`). A facet
whose range was not read shows no `range` key (`FilterFacet.range` is left out
of the dump), and the options tool's `query` argument says that a query naming a
range facet returns its range. A read
runs inside the site's search line, and the result is held in a cache of 512
entries on the site catalog, keyed by the search, the parameter, the term, the
parent context and the other clauses.

# A filter that selects nothing is refused as wdk-client refuses it

`read_under_parents` refuses, on every path that reads a value:

- a bound range that selects none of its facet's range, with the range and its
  units (`EmptyRangeError`: "total_variants (Total variants) on
  gene_variant_stats spans 1 to 4,823 variants over 5,643 records;
  {"min": 4824.0} selects none of it. State a range inside it.");
- a value whose selected count is known and below the parameter's
  `minSelectedCount` (`TooFewSelectedError`). The count is `nativeFiltered`
  from `POST .../{param}/summary-counts`, and a count that is not known passes.
  That is wdk-client's `isParamValueValid`
  (`filteredCount == null || minSelectedCount <= filteredCount`); WDK itself
  does not check `minSelectedCount`.

# Rejected

**The filter shorthand.** A text such as `facet>=5` was parsed into a clause.
Text the parser did not recognize became the empty filter and was recorded as
the researcher's own statement: `'total_variants>5'`, `'total_variants > 5'`
and `'totl_variants>=5'` each gave `{"filters": []}`, so "more than 5 variants"
selected every gene. A name was matched by substring, so `variants` bound
`total_variants`. The shorthand took one facet only, could not state
`includeUnknown`, and its rule text was copied into six places. It is removed
everywhere, the served `resolve_search_parameters` included.

**A clause whose type the statement supplies.** A JSON clause once defaulted to
`type: "string"` and `isRange: false`. WDK does not check a string clause
against a numeric range term, so `["0", "0.05"]` on a range facet ran as
`IN ('0', '0.05')`. The facet holds the type, so the statement does not state
it.

**Reading every range of a sheet.** A term summary returns one count per
distinct value. For `pi_per_site_cds` on `GenesByVariantCharacteristics` it is
292,394 bytes (3,212 values), and that parameter has 15 range facets. A
whole-sheet read on every bind or options read multiplies that by the facets,
while a refusal needs only the facet a clause binds.

**Bounds that exclude their end.** WDK reads a range as inclusive, with a null
bound unbounded. `>` and `<`, and `gt` or `lt` fields, would state a bound WDK
cannot hold, so only inclusive bounds are accepted.

# Anchor

`FilterProposal`, `FilterProposals`, `FilterFacet`, `FilterFacets`,
`FacetRange`, `FilterValue` and the clause classes in veupathdb-py
`domain/parameters/filter_clause.py`; `refuse_filter_misses`, `with_ranges`,
`WDKFilterReads`, `EmptyRangeError` and `TooFewSelectedError` in veupathdb-mcp
`catalog/facet_ranges.py`; `read_under_parents` in `catalog/param_dag.py`;
`ParameterInfo.filter_fields` in `catalog/param_formatting.py`;
`filterParamLogic.ts` in `apps/web/src/features/strategy/editor/widgets/`.
Rule WDK-PARAM-018 in
`veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`.
Guarded by `tests/integration/strategies/test_a_variant_filter_binds.py`,
`tests/unit/services/strategies/test_a_filter_reads_with_its_field_names.py`,
`tests/unit/domain/strategy/test_a_range_reads_as_its_bounds.py` and
`tests/unit/ai/tools/test_frame_reads_a_value_by_its_parameter.py`.
