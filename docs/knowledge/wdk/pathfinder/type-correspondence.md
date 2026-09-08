---
type: Reference
title: What corresponds to what
description: A four-column map from WDK's Java model to wdk-client, to PathFinder's Pydantic, to the TypeScript the browser sees - and an explicit account of every cell that is empty.
tags: [wdk-alignment, types, correspondence, pathfinder]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

Every permalink below is pinned to the sha recorded in sources.md (`veupathdb-py: docs/knowledge/wdk/sources.md`).

# How to read an empty cell

There are four representations of the same concepts, and a concept can be absent
from any of them for two entirely different reasons. **An empty cell that reads
as an oversight is worse than one labelled "none, deliberately"**, so every
absence in the tables below carries one of two words:

- **none, deliberately** - PathFinder chose not to have the type, and the reason
  is recorded in [deliberate-divergences](deliberate-divergences.md).
- **none** - no such type exists here and no decision records why. Treat that as
  the drift risk it is.

A cell naming a type that is *not* the corresponding type - `Strategy` in
`@pathfinder/shared` is not a WDK strategy - says so in the cell. Sharing a name
is exactly how the wrong type gets used.

# Two splits PathFinder makes that upstream does not

Both tables read strangely until these are stated, because a single upstream type
lands in two PathFinder types.

**A parameter is split into a spec and a value.** WDK's `Param` and wdk-client's
[`Parameter`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L224-L234)
are one type carrying both the declaration (vocabulary, bounds, `dependentParams`)
and the current value, as `initialDisplayValue` on
[`ParameterBase`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L54-L64).
PathFinder splits them: the declaration is `WDKParameter` in
`veupathdb/wdk/wdk_parameters.py`, and the value is `ParamValue` in
`domain/parameters/values.py`. The declaration is an integration concern and the
value is a domain concern, and only the value crosses layers.

**Structure is split from data.** WDK already does this on the wire -
[`StrategyDetails`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkUser.ts#L120-L124)
carries `stepTree` and `steps` separately - and PathFinder goes one step further
by flattening the tree into parent pointers everywhere except the WDK boundary
([nested-tree-at-the-wire-boundary](../../decisions/nested-tree-at-the-wire-boundary.md),
[WDK-MAP-003](rules/pathfinder-mapping.md)).

# The structural concepts

| Concept | WDK Java | `wdk-client` | PathFinder Pydantic | `@pathfinder/shared` |
|---|---|---|---|---|
| strategy | [`Strategy`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L39-L47) | [`StrategyDetails`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkUser.ts#L120-L124) extending [`StrategySummary`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkUser.ts#L103-L119) | `WDKStrategyDetails` / `WDKStrategySummary` | **none, deliberately.** `Strategy` in `types.ts` is a conversation, not a WDK strategy - see below |
| step tree | **no dedicated class.** In memory it is `TreeNode<Step>` from fgputil, built in [`Strategy`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L310-L335); the JSON is written by [`StepFormatter.formatAsStepTree`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepFormatter.java#L129-L140) | [`StepTree`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkUser.ts#L145-L150) | `WDKStepTree` | **none, deliberately.** Flattened to `StepResponse.primaryInputStepId` / `secondaryInputStepId` |
| step | [`Step`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L43-L52) | [`Step`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkUser.ts#L59-L79), extending `AnswerSpec` | `WDKStep` | **none, deliberately.** `Step = StepResponse` is PathFinder's step, which may not exist in WDK at all |
| search config | [`AnswerSpec`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/answer/spec/AnswerSpec.java#L30-L45), serialized by [`AnswerSpecServiceFormat.format`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/answer/AnswerSpecServiceFormat.java#L100-L117) | [`SearchConfig`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L377-L385) | `WDKSearchConfig` | **none, deliberately.** Its parts arrive separately as `StepResponse.parameters` and `StepResponse.filters` |
| search | [`Question`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/question/Question.java#L69-L78) | [`Question`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L252-L279) and [`QuestionWithParameters`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L280-L283) | `WDKSearch`, enveloped by `WDKSearchResponse` | `Search = SearchResponse` - **four fields, a listing entry, not the search document** |
| record class | [`RecordClass`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/record/RecordClass.java#L94-L102) | [`RecordClass`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L28-L43) | `WDKRecordType` | `RecordType = RecordTypeResponse` - **three fields, a listing entry** |
| answer | [`AnswerValue`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/answer/AnswerValue.java#L132-L145) | [`Answer`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L361-L376) | `WDKAnswer`, `WDKAnswerMeta`, `WDKRecordInstance` | **none, deliberately.** `RecordsResponse` / `RecordsMeta` / `RecordAttribute` are PathFinder's own projection and drop `viewTotalCount` and `displayViewTotalCount` |
| filter (applied) | [`Filter`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/filter/Filter.java#L17-L32) | element of [`FilterValueArray`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L386-L390) | `WDKFilterValue` | `StepFilter` |
| filter (declared) | [`FilterDefinition`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/filter/FilterDefinition.java#L120-L136), published by [`QuestionFormatter.getFiltersJson`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/QuestionFormatter.java#L110-L118) | [`QuestionFilter`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L245-L250) | **none.** `WDKSearch.filters` is `list[JSONObject]`, so this concept is parsed untyped | **none** |
| reporter | [`ReporterRef`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/ReporterRef.java#L28-L39) | [`Reporter`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L45-L52) | `WDKReporter` | **none, deliberately.** `StepReport` names a reporter (`reportName`, defaulting to `standard`) but does not describe one - no `scopes`, no `isInReport`, so nothing in the browser can offer a choice |
| attribute field | [`AttributeField`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/record/attribute/AttributeField.java#L41-L52) | [`AttributeField`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L314-L324) | `WDKAttributeField` | `RecordAttribute` - PathFinder's own seven-field projection, with an `isSuggested` WDK does not have |
| step analysis | [`StepAnalysis`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/analysis/StepAnalysis.java#L8-L25) (the type) and [`StepAnalysisInstance`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/analysis/StepAnalysisInstance.java#L50-L70) (the run) | [`StepAnalysisType`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/StepAnalysisUtils.ts#L25-L35) and [`StepAnalysisConfig`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/StepAnalysisUtils.ts#L53-L65) | `WDKStepAnalysisType` / `WDKStepAnalysisConfig` | `StepAnalysis` - **a request PathFinder will make, not an instance WDK has** |

Two rows repay a second look.

**`Search` and `RecordType` in `@pathfinder/shared` are listing entries, not
documents.** `SearchResponse` is `{name, displayName, description, recordType}`
and `RecordTypeResponse` is that minus `recordType`. Neither can express what
WDK's `Question` carries - `paramNames`, `groups`, `allowedPrimaryInputRecordClassNames`,
`defaultAttributes`. The full parameter picture reaches the browser through
`ParamSpecResponse` instead, which is a normalized flat spec rather than a
discriminated union (next section).

**The declared-filter row is the one row whose Pydantic cell is a raw dict.**
`WDKSearch.filters` is `list[JSONObject]`, so the three filters every transcript
search advertises (filters, `veupathdb-py: docs/knowledge/wdk/model/filters.md`) arrive unparsed. It is not
PathFinder's only untyped field - `wdk_models.py` declares nine `JSONObject` or
`JsonValue` fields in all, among them `dynamicAttributes`, `summaryViewPlugins`
and `columnFilters` - but it is the only one standing in for a concept this table
names. No consumer of it was found: `search.filters` and `searchData.filters`
appear nowhere outside the model definition, which is why it has survived.

# The eleven parameter kinds

`ParamKind` in `domain/parameters/values.py` is WDK's eleven
[`*_PARAM_TYPE` constants](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/core/api/JsonKeys.java#L147-L157)
and nothing else (WDK-PARAM-001 in
`veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`,
[WDK-MAP-001](rules/pathfinder-mapping.md)). The Java column names the class
[`ParamFormatterFactory`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/ParamFormatterFactory.java#L18-L55)
dispatches on to produce that `type` string.

| `type` | WDK Java | `wdk-client` | PathFinder spec / value | `@pathfinder/shared` value |
|---|---|---|---|---|
| `string` | [`StringParam`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/StringParam.java#L171-L203) | [`StringParam`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L66-L71) | `WDKStringParam` / `StringValue` | `StringValue` |
| `number` | [`NumberParam`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/NumberParam.java#L32-L40) | [`NumberParam`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L188-L193) | `WDKNumberParam` / `NumberValue` | `NumberValue` |
| `number-range` | [`NumberRangeParam`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/NumberRangeParam.java#L96-L146) | [`NumberRangeParam`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L195-L200) | `WDKNumberRangeParam` / `NumberRangeValue` | `NumberRangeValue` |
| `date` | [`DateParam`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/DateParam.java#L135-L170) | [`DateParam`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L202-L206) | `WDKDateParam` / `DateValue` | `DateValue` |
| `date-range` | [`DateRangeParam`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/DateRangeParam.java#L154-L207) | [`DateRangeParam`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L208-L212) | `WDKDateRangeParam` / `DateRangeValue` | `DateRangeValue` |
| `timestamp` | [`TimestampParam`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/TimestampParam.java#L30-L40) | [`TimestampParam`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L73-L75) | `WDKTimestampParam` / `TimestampValue` | `TimestampValue` |
| `single-pick-vocabulary` | [`AbstractEnumParam`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L73-L90) with `isMultiPick` false - concretely [`EnumParam`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/EnumParam.java#L22-L30) or [`FlatVocabParam`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/FlatVocabParam.java#L30-L40) | four interfaces, [`SinglePick{Select,CheckBox,TypeAhead,TreeBox}EnumParam`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L144-L167) | `WDKEnumParam` / `SinglePickValue` | `SinglePickValue` |
| `multi-pick-vocabulary` | the same classes with `isMultiPick` true; the choice is made in [`EnumParamFormatter`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/EnumParamFormatter.java#L45-L50) | four interfaces, `MultiPick{Select,CheckBox,TypeAhead,TreeBox}EnumParam` | `WDKEnumParam` / `MultiPickValue` | `MultiPickValue` |
| `filter` | [`FilterParamNew`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/FilterParamNew.java#L85-L98) | [`FilterParamNew`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L77-L110) | `WDKFilterParam` / `FilterValue` | `FilterValue` |
| `input-dataset` | [`DatasetParam`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/DatasetParam.java#L41-L50) | [`DatasetParam`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L214-L218) | `WDKDatasetParam` / `InputDatasetValue` | `InputDatasetValue` |
| `input-step` | [`AnswerParam`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AnswerParam.java#L44-L56) | [`AnswerParam`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L220-L222) | `WDKAnswerParam` / `InputStepValue` | `InputStepValue` |

**Two type names do not match their `type` string, in both upstreams and in
PathFinder.** `input-dataset` is served by a class called `DatasetParam` and
`input-step` by one called `AnswerParam` - the Java name, the wdk-client name and
PathFinder's `WDKAnswerParam` all say "answer" where the wire says "step".
Grepping WDK's source for `input-step` finds the `JsonKeys` constant and the
formatter, never `AnswerParam.java`.

**Both parameter unions have ten members for eleven types.** wdk-client's
`Parameter` collapses the eight enum interfaces into `EnumParam`; PathFinder's
`WDKParameter` collapses the two vocabulary types into `WDKEnumParam`, whose
`type` field is a two-member `Literal`. The arithmetic is a coincidence of two
different collapses, not an alignment - and neither ten is the number of
parameter *types*, which is eleven.

# The parameter spec has no discriminated union on the wire

The value column above is faithful: eleven Pydantic models generate eleven
TypeScript types, one per model, and `StepResponse.parameters` is an
eleven-branch discriminated union over them.

The **spec** column stops at the service layer. `ParamSpecResponse` requires only
`name` and `type` and makes every kind-specific field optional, so `vocabulary`,
`min`, `max`, `ontology`, `parsers` and `defaultIdList` all hang off one object
with `type: string` rather than a discriminant. The browser cannot ask the type
system which fields a `filter` parameter has; it reads `type` and knows by
convention.

That is a real gap and it is not recorded as a decision anywhere, which is why it
is stated here rather than in [deliberate-divergences](deliberate-divergences.md).
The eleven-way discriminated union already exists on the value side, so the
machinery is not the obstacle.

# What lives where, in one sentence each

- **`veupathdb/wdk/wdk_models.py`** - every `WDK*` response model, one per
  WDK JSON document. Frozen, `extra="ignore"`, camelCase aliases. Nothing outside
  the integration layer constructs these from raw JSON.
- **`veupathdb/wdk/wdk_parameters.py`** - the ten-member `WDKParameter`
  union, discriminated on `type`.
- **`domain/parameters/values.py`** - the eleven `*Value` models and `ParamKind`.
  Pure, no I/O, and the only parameter representation that crosses layers.
- **`domain/parameters/value_codec.py`** - the conversion between those models and
  WDK's wire and decoded forms, and the coercion of raw input into one of them.
- **`domain/parameters/wdk_vocab.py` and `domain/wdk_values.py`** - the eight
  `WDK*`-named types that reach the browser, listed in
  [WDK-MAP-007](rules/pathfinder-mapping.md). They are WDK-shaped and
  domain-owned, which is not a contradiction: they carry no I/O.
- **`packages/shared-ts/src/generated/`** - Kubb output from `openapi.json`. Never
  edited by hand ([one-way-to-generate-types](../../decisions/one-way-to-generate-types.md)).
- **`packages/shared-ts/src/types.ts`** - the hand-written remainder: the combine
  operator enum, the site catalog, and `StrategyAst`.
