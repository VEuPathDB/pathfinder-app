---
type: Decision
title: A value is read by its parameter
description: The WDK parameter declaration says what JSON a model states for it, reads that statement, writes the wire string and gives the one refusal; every tool takes native values and the typed wrapper stays for HTTP, storage and the web. A static discriminated union in the tool signature and the typed wrapper for the model were rejected.
tags: [parameters, wdk-alignment, frame, agents]
generated: { by: claude-code/opus-5.5, at: 2026-11-21T00:00:00Z }
status: stable
---

# What was decided

A parameter's declaration owns the shape a model states for it. veupathdb-py
`stated_reading(param)` (`domain/parameters/stated.py`) builds one Pydantic
`TypeAdapter` per kind from the declaration. Its JSON schema is what the model
sees (`WDKBaseParameter.stated_schema()`, served as
`ParameterInfo.stated_schema`), its parse is what the model is held to
(`read_stated`), and the value it gives writes the wire string through the
existing `to_wire`. A statement that does not parse is refused once, with the
parameter's shape and an example (`StatedValuesError`). No other reader of a
model's value exists.

The model states native JSON. A number is a number, a range is
`{"min": .., "max": ..}`, a date is `"yyyy-mm-dd"`, a single pick is one term, a
multi-pick is a list of terms, a dataset is its id or a list of ids, and a step
input is `""` or digits. The rules are WDK's:

- A string with `isNumber` is written as the shortest decimal, never an
  exponent: `5.0` goes out as `"5"` and `1e-8` as `"0.00000001"`. `NaN`,
  `inf` and a boolean are refused.
- A number is checked against the published `min` and `max`.
- A date is ISO `yyyy-mm-dd` (`ISODate`). `20200101` and week dates are
  refused, since `DateRangeParam` parses a bad bound unguarded and answers 500.
- A pick is an exact term. A flat vocabulary of at most 50 terms whose display
  type is not `typeAhead` is an `enum` in the schema, for a single pick and for
  each item of a multi-pick. A boolean stated for a `yes`/`no` vocabulary is refused
  with the terms named.
- A dataset id is a positive integer and a step id is `""` or digits.
- An empty value (`""`, and `[]` for a multi-pick) is read only where the
  parameter publishes `allowEmptyValue: true`, as `Param.validate` decides it
  for every kind before the kind's own check (WDK-PARAM-019). There the schema
  offers `""` and it reads as the kind's empty value (`empty_value`: no number,
  no date, no range end, `""` or `[]`); elsewhere it is refused, by the reader
  and by the canonicalizer on the typed path. A filter's empty value goes out as
  `""` and is not `{"filters":[]}`, the value with no clauses the editor writes and
  `FilterParamNew` defaults to; that one is stated `[]`, and `[]` reads back to it. `GenesByNgsSnps.occurrences_upper` takes `""` for no upper bound,
  and a required multi-pick refuses `[]`; a value left out runs at the site's
  default. A multi-pick holds `minSelectedCount` to `maxSelectedCount` terms,
  so `GenesByLocation.organismSinglePick` takes exactly one.

A value WDK holds is read, never refused or rewritten
(`ParameterCanonicalizer.held`). A wire form no kind reads, the value of a name
with no spec, and every value of a step whose search spec cannot be read is a
`HeldValue` (`{"type": "held", "wire": ..}`) in the step's one parameter map,
exactly as WDK holds it, with WDK's own step validation beside it in
`step_validations`. Every path that copies, compares or re-runs the map carries
it; every push sends `wire_map(parameters)`, so it goes back unchanged; a
comparison with the site reads both sides on the wire; and only a stated value
replaces it. A value is canonical once, when it is stated: the FRAME bind, an
edit (validated with the step's other values as context, so only the names it
states are canonicalized or refused and only they are written; the guard reads
what the catalog makes of the whole map, so a cascade is still refused), a variant and a separation candidate read a stated
branch as its leaves and a stated census pattern in census order. The map then
holds only stated canonical values and values read from WDK, so every push sends
`wire_map(parameters)` as it is, and the client shapes nothing, a search report
included; the push judges nothing and only adds a site-set value the step lacks.
WDK's verdict on a value the step already holds never refuses a statement, and
a general error refuses only a statement that adds it to the step's stored
verdict. The guard reads the values it compares without refusing them. A read value WDK holds, a branch term
included, is never canonicalized because a sibling was edited.

A stated value is canonical from the moment it is stated, and a push sends the
step's values as the step holds them. A curated seed or gold tree is a statement
too, canonicalized where it becomes steps (`commit_tree`). A step
stored earlier that holds a stated branch is not migrated: it is pushed as held. The agent reads a held
value as "kept as the site holds it", no stated schema offers the kind, and the
editor shows its raw text and leaves it out of a patch until it is edited. A value
stated back as shown, its stated form or a kept value's marked text or wire, is the held
value: the one reader that knows the held values (`read_under_parents`, through `bound`)
takes it without reading it, for a FRAME rebind, a variant, an edit and a typed operation
alike, while no parent of it reads to a new value. A parent moves only when its read value
is not `==` to the held one, so the same organism stated in another case, or the same
organisms in another order, moves nothing. Every path that binds a value reads it through
`read_under_parents` with the held values as `bound`, and the reader returns
`BoundValues`, an mcp mapping whose constructor takes a sentinel only the reader module
holds and checks by identity, and whose values cannot change; ruff's banned-api rule
(`TID251`) refuses an import or attribute read of the sentinel here and in mcp. The type
ends at three named sinks: `CriterionCall.with_read`, the variant builder `_variant_spec`
and the control-test `control_config` take `BoundValues`, so a raw dict there fails mypy and
pyright. The reader module's own writers (`typed_tree`, `typed_operation`) and the edit tool
copy a reading into `StrategyStepNode`, `UpdateStepParamsOp` and `AddLeafOp`, and those
models take plain maps, because the already-bound writers below feed them too.
`CriterionCall.with_values` takes plain maps for the same reason: it is called with held
values (`with_held`) and with read values rewritten to the site's scale or open ends
(`_frame_sources`, `_frame_values`), never with stated values, which reach the call through
`with_read`. Held, replayed and measured values are
already bound, so their writers keep plain mappings; the binding test names each one with
its reason (`ALREADY_BOUND`) and fails when another writer of `bind_values` appears. One
parametrized test drives eight paths (a FRAME rebind, a variant, an edit, a typed
operation, an options read, a card pick, a build and a control test) through five cases.

Equality is on the value types (veupathdb-py `KindValue`): `==`, `in`, sets, dict keys and
model equality compare a value by its identity in its own kind, and a held value meets a
typed one in the typed value's kind. `same_param_value(name, kind, ...)` is the one
function that takes a kind, for two held values or the phyletic expression; Strategist uses
it where a site-held value meets the step's (`site_changes`) and where two offered wires
meet (`AcceptedReading.same_reading`), with the kind of the bound value. Strategist holds no
equality of its own.

The bar is that an honest change cannot regress silently: the value types (`==` on each
kind) and the `BoundValues` sinks enforce equality and binding. Deliberate circumvention
(`vars()`, `getattr` with a built name, an `Any` reaching the sentinel, a lambda) is outside
the bar, and nothing chases it. Two gates are best-effort first lines, not proofs.
`python -m veupathdb.devtools.param_equality` runs in
pre-commit and CI here and in both libraries; it fails on the forms of comparing wire text
it names (`==`, `!=`, a wire on the left of `in`, a count of distinct wires, a set, a local,
`str()`, `model_dump()` or `.get` of one) outside the client's equality module, and each repository lists its allowed text
comparisons in `scripts/param-equality-allowed.txt`. The unit test
`test_every_binding_reads_through_the_one_reader.py` derives the mcp functions that bind
from mcp's source and the reader entries from the three reader modules (`_stated_values.py`,
`_frame_proposals.py`, `sheet_params.py`); it fails when another module reaches a binder by
import, attribute or `getattr`, when a tool function that calls a reader entry is not mapped
to a path, and when a mapped tool no longer binds. The build and the control test hold no
value, so their paths assert that every stated value is read under the stated parent. A held
value whose parent moved is read again under the new parent, whether the call gives it back
or leaves it out, so an edit that moves an organism refuses a filter the new organism does
not hold instead of pushing it unread. That refusal (`MovedParentError`) names the parent and
its old and new value, the child and what it held, the reader's own refusal, at most five
ranked entries under the new parent the refusal did not already list, and asks to state the
child again or leave it out. A child the call states anew is read and refused in the reader's
own words. An options read never refuses for a held sibling: it reads its context with
`read_stated_context` (`typed_context_read`), answers the asked parameter under it, and
appends each held value that no longer reads there to the result's `note` in the same words,
binding nothing; a context value the agent states wrongly is refused, and the write that
keeps the stale value still refuses it. Every value an agent may state back is shown whole; a summary that cuts a value says
it was cut and how long it was.

The rejected alternative kept held values in a second map beside `parameters`
and merged them at the push. Every path that copies, compares, validates or
re-runs `parameters` then had to know the second map, and the ones that did not
dropped or rewrote held values.

Every tool that takes a parameter value reads it through the declaration:
`set_criterion`, `propose_readings`, the edit tools, the tree tools
(`build_strategy`, `replace_subtree`, `apply_operations`) and the served
`resolve_search_parameters`. The tree tools take native values through their
own stated node types (`_stated_values.py`) and refuse the wrapper. The typed
wrapper (`ParamValue`, `{"type": .., "value": ..}`) stays for HTTP, storage and
the web, where the kind is known without a declaration.

# A value is read under its bound parents, by one reader

A dependent parameter's vocabulary and facets come from its parents, so a
value is read against the declarations the site gives under the values bound
before it. veupathdb-mcp `read_under_parents` is the one reader: each pass
reads the values whose parents are bound, adds the site-set values those
parents give, and fetches the declarations again under the new context. A
caller that holds a step's values passes them as `bound`, so an edit reads a
dependent value under the step's own parents. The FRAME card check, the edit
tools and the served reads call it; the options read calls it with `stale`, through
`read_stated_context`, so a held sibling that no longer reads is noted rather than
refused. None reads a value against the published sheet.

# A seed keeps WDK's wire value

The curated strategies under `strategist_scripted/seeds/data/` store the wire value WDK would send,
read by `from_wire` for the parameter's kind. A seed is not a model statement,
so it is not read by `stated_reading`. A test reads every seed value of a
recorded declaration through it and finds no refusal.

# A dataset is saved through the site route

A dataset is its WDK id. The step editor saves its source (an id list typed or
read from a file, a basket or a strategy) through `POST /api/v1/sites/{siteId}/datasets`, which
answers `{"datasetId"}`, and commits that id as the value. It saves a source
only when it differs from the last one saved, and an empty id list saves
nothing. `set_criterion` also takes a list of ids and saves it as an id list.

# Rejected

**A static discriminated union in the tool signature.** A union of the eleven
value models in each tool's arguments cannot say which member belongs to which
parameter, so a number range would still be accepted for a pick. In pydantic-ai
2.66 such a union is not strict-compatible, and the model can leave `type` out.
The schema is per parameter instead: FRAME attaches each open parameter's
`stated_schema` at prepare time (`_frame_schema.name_the_open_sheets`), and every
other tool reads a `dict[str, JsonValue]` through the declaration.

**Keeping the typed wrapper for the model.** The wrapper was the shape the
refusal asked for, and the binder did not read it back. A number stated as
`{"type": "number", "value": 5}` was refused with a request for the same
shape, a loop that never bound the value. A string wrapper reached WDK as its
JSON text. A wrapper adds a field the declaration already knows.

**A shape guess per caller.** `param_value_from_raw`, `coerce_context_values`
and the proposal coercion each decided a kind from the value's shape and wrote
`True`, `"true"` or `"1"` for a boolean. They are deleted. The kind is the
declaration's.

# Anchor

`stated_reading`, `StatedReading`, `StatedValuesError` and `read_stated_values`
in veupathdb-py `domain/parameters/stated.py`; `ISODate` in
`domain/parameters/date_bounds.py`; `decimal_text` in
`domain/parameters/decimals.py`; `stated_schema`, `read_stated` and
`stated_example` on `WDKBaseParameter` in `wdk/wdk_parameters.py`;
`ParameterInfo.stated_schema` in veupathdb-mcp `catalog/param_formatting.py`;
`read_under_parents`, `MovedParentError` and `read_declared` in `catalog/param_dag.py`;
`read_stated_parameters` and `read_stated_context` in `catalog/search_inspection.py`;
`typed_values`, `typed_context_read` and
the stated node types in `ai/tools/standalone/_stated_values.py`;
`name_the_open_sheets` in `ai/tools/standalone/_frame_schema.py`; the dataset
route in `transport/http/routers/sites/datasets.py`; `DatasetParam.tsx` in
`apps/web/src/features/strategy/editor/widgets/`.
Guarded by `tests/unit/ai/tools/test_a_tool_reads_native_values.py`,
`tests/unit/ai/tools/test_frame_reads_a_value_by_its_parameter.py`,
`tests/unit/ai/tools/test_a_reading_reads_native_values.py`,
`tests/unit/ai/tools/test_an_edit_reads_under_the_steps_own_values.py`,
`tests/unit/ai/tools/test_a_dataset_parameter_takes_typed_ids.py`,
`tests/unit/ai/capabilities/test_a_value_error_asks_for_no_wrapper.py`,
`tests/unit/scripted/seeds/test_a_seed_value_reads_by_its_parameter.py`,
`tests/unit/transport/test_a_list_of_ids_is_saved_as_a_dataset.py` and
`tests/integration/http/test_a_dataset_is_saved_through_the_site_route.py`.
