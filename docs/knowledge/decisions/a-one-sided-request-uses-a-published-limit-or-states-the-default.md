---
type: Decision
title: A one-sided request uses a published limit or states the default
description: A typed requirement that states one side of a range binds the other end of a number-range parameter at its published limit, else at its default; no typed data pairs two number parameters, so a step that holds them keeps the site defaults and states them under the linked parameter. Inventing a floor and asking every time were rejected.
tags: [parameters, ranges, requirements, wdk]
generated: { by: claude-code/opus-5.5, at: 2026-11-03T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-11-03T00:00:00Z }
status: stable
---

# What was decided

`CountValue.side` and `PercentileValue.side` read which side of a range a typed
requirement states: `>=`, `>` and a top share state the lower side; `<=`, `<` and a
bottom share state the upper side; `=` states neither. No text is read for it.

**A range parameter.** `number-range` is one parameter with two ends, so its pairing
is typed. When `set_criterion` binds a proposed range and the requirements linked to
it state one side, `domain/strategy/one_sided.py::with_open_ends_bound` sets the other
end to the published `min` or `max`, else to that end of the published default. The
tool result names the change in `corrections`, and the step row says which it holds.
An end that would cross the stated bound leaves the proposal as it is, and a
parameter proposed as null keeps its default whole.

**Two number parameters.** Nothing served pairs them, so nothing here does. A step
that links a one-sided requirement to a number parameter keeps its other values, and
the row of that parameter states the requirement, the side it does not state, and
every number the step holds at the site default:

```
The request states 'molecular weight under 30 kDa' and no lower bound. Site defaults this step holds: Min Molecular Weight 10000
```

The sentence claims nothing about which default is the other end of what. A step
where a linked requirement states the other side adds nothing, and so does a step with
no requirement linked to a side.

**Ends that cross.** The bound and the default are compared as numbers. When a listed
default is past the linked value, the note says so, and it stays conditional because
nothing pairs the two:

```
Minimum expression percentile 80 is above Maximum expression percentile 10. If these two bound one range, it holds no value as bound, since the low end is above the high end
```

No bound moves: the site's default stays, as this decision holds. WDK does not refuse
this request. `StringParam.validateValue` checks that a number parses and reads no
other parameter, so both values reach the search's query, and what the query returns
is not measured here. A `number-range` cannot reach this state: `NumberRangeValue`
refuses a minimum above its maximum, `NumberRangeParam.validateValue` refuses it on the
site, and an open end that would cross the stated bound leaves the proposal as it is.

**The verdict.** `CountValue` holds a number and no unit, so "under 30 kDa" holds 30
while its parameter holds 30000. A count is not compared with the end of a range, and
a linked parameter whose number is a power of ten from the stated number is not
verified, with that reason, only when every unmet reading of the count is such a
parameter. Any other difference stays a miss, beside it or not. A real miss by exactly
a power of ten reads as not verified, not as a failure. The verdict does not move the
edit guard: `stated_values` also reads every parameter a stated count links, so a
rewrite of that value is refused whatever the verdict says.

# The measurement

`NumberParam` and `NumberRangeParam` carry optional `min` and `max` in the WDK Java and
in `wdk-client`. On QA, 28 searches on PlasmoDB and FungiDB and Molecular Weight on
MicrosporidiaDB serve every numeric bound as `type: string` with `isNumber: true` and
no `min` or `max`: molecular weight 10000 and 50000, exon count 2 and 20, expression
percentile 80 and 100. Of 24 other PlasmoDB searches read on QA, one held a parameter
with published limits: `GenesByIntronJunctions.percent_max`, a `number-range` with
`min` 1, `max` 100 and default `{"min":"20","max":"100"}`, recorded in
`tests/fixtures/wdk/search_genes_by_intron_junctions.json`.

The two bounds of a pair share the group `empty` with every other parameter of the
search, and `GenesByNgsSnps` holds three such pairs in one group. Only their names and
display names relate them.

# What was rejected

**Inventing a floor such as 0.** A site that publishes no minimum says nothing of 0.
A molecular weight floor of 0 reads as harmless, and the same rule on a score or a
log value states a bound no one measured. The default is what the site offers, and the
row says it is the default.

**Asking every time.** A card on each one-sided request stops the build for a bound
the researcher chose not to state. The stated sentence carries the same fact beside
the count, and the researcher can restate a bound.

**Pairing by name.** A `min_` and `max_` prefix, or words such as "Minimum" and
"Maximum" in a display name, hold on some searches and not on others
(`occurrences_lower`, and `max_flanking_bp` with no partner). A rule on
them changes a search on a guess.

**Pairing by position on the sheet.** Neighbours on the sheet are usually a pair, but
the site does not state it, and a wrong pair changes the count with no error.

# What would change this

A site field that names the other end of a parameter, or a number-parameter pair
served as one `number-range`. With either, the two-parameter case binds as the range
case does. The library holds `min` and `max` on `ParameterInfo` already.
