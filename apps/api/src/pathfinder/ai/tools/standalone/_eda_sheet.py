"""The EDA filter sheet: every filterable variable, with one example to copy."""

from __future__ import annotations

from assistant_core.platform.types import JSONObject
from pydantic import JsonValue
from veupathdb.domain import walk_entities

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.tools.standalone._eda_models import EdaFilterSheetEntry
from pathfinder.services.eda import EdaStudyDetail
from pathfinder.services.eda.description import (
    EdaVariableOut,
    children_of,
    entity_facts,
    variable_facts,
    variable_out,
    vocabulary_note,
    with_time_part,
)

# A vocabulary the study cut is a sample of a form, not a list of values: the
# model reads the distribution to learn which values the subset holds, so a
# shorter sample says the same thing.
_SAMPLE_OF_A_CUT_VOCABULARY = 8

_RE_SHEET_NOTE = (
    "vocabulary shown in the first sheet for this study; ask "
    "preview_eda_subset for this variable's distribution to see the values "
    "the current subset holds"
)

_LONGITUDE_EXAMPLE = (-180.0, 180.0)


def _example(entry: EdaVariableOut, *, first_values: dict[str, str]) -> JSONObject:
    """One complete filter object for this variable, built from what it declares."""
    example: JSONObject = {
        "entityId": entry.entity_id,
        "variableId": entry.variable_id,
        "type": entry.filter_type,
    }
    strings: list[JsonValue] = list(entry.vocabulary[:1])
    match entry.filter_type:
        case "stringSet":
            example["stringSet"] = strings
        case "numberSet":
            numbers: list[JsonValue] = [float(v) for v in entry.vocabulary[:1]]
            example["numberSet"] = numbers
        case "dateSet":
            dates: list[JsonValue] = [with_time_part(v) for v in entry.vocabulary[:1]]
            example["dateSet"] = dates
        case "numberRange":
            example["min"] = entry.range_min
            example["max"] = entry.range_max
        case "dateRange":
            example["min"] = entry.date_min
            example["max"] = entry.date_max
        case "longitudeRange":
            example["left"], example["right"] = _LONGITUDE_EXAMPLE
        case _:
            sub_filters: list[JsonValue] = [
                _sub_filter_example(child, first_values)
                for child in entry.sub_filter_variable_ids[:2]
            ]
            example["operation"] = "union"
            example["subFilters"] = sub_filters
    return example


def _sub_filter_example(variable_id: str, first_values: dict[str, str]) -> JSONObject:
    """One sub-filter, with a value the child variable really carries."""
    value = first_values.get(variable_id)
    members: list[JsonValue] = [] if value is None else [value]
    return {"variableId": variable_id, "stringSet": members}


def _sheet_entries(study: EdaStudyDetail) -> list[EdaFilterSheetEntry]:
    """Every filterable variable of the study, with an example to copy."""
    described: list[tuple[str, EdaVariableOut]] = []
    first_values: dict[str, str] = {}
    for entity in walk_entities(study.root_entity):
        entity_name = entity_facts(entity).display_name
        for variable in entity.variables:
            facts = variable_facts(variable)
            if facts.vocabulary:
                first_values[facts.id] = facts.vocabulary[0]
            out = variable_out(
                entity_id=entity.id,
                facts=facts,
                sub_filter_variable_ids=children_of(entity, variable.id),
            )
            if out is not None:
                described.append((entity_name, out))
    return [_entry(entity_name, out, first_values) for entity_name, out in described]


def _entry(
    entity_name: str,
    out: EdaVariableOut,
    first_values: dict[str, str],
) -> EdaFilterSheetEntry:
    """One sheet entry, with the sample of a cut vocabulary cut further."""
    filter_type = out.filter_type
    if filter_type is None:
        msg = f"Variable {out.variable_id} reached the sheet with no filter type"
        raise ValueError(msg)
    vocabulary = out.vocabulary
    note = out.vocabulary_note
    if out.vocabulary_total > len(vocabulary):
        vocabulary = vocabulary[:_SAMPLE_OF_A_CUT_VOCABULARY]
        note = vocabulary_note(total=out.vocabulary_total, shown=len(vocabulary))
    return EdaFilterSheetEntry(
        entity_id=out.entity_id,
        entity_display_name=entity_name,
        variable_id=out.variable_id,
        display_name=out.display_name,
        filter_type=filter_type,
        is_multi_valued=out.is_multi_valued,
        vocabulary=vocabulary,
        vocabulary_total=out.vocabulary_total,
        vocabulary_note=note,
        range_min=out.range_min,
        range_max=out.range_max,
        date_min=out.date_min,
        date_max=out.date_max,
        sub_filter_variable_ids=out.sub_filter_variable_ids,
        example=_example(out, first_values=first_values),
    )


def sheet_for(
    domain: StrategyDomainState,
    study: EdaStudyDetail,
    dataset_id: str,
) -> list[EdaFilterSheetEntry]:
    """The sheet for one study, without repeating a vocabulary."""
    entries = _sheet_entries(study)
    if not domain.was_eda_sheet_shown(dataset_id):
        domain.mark_eda_sheet_shown(dataset_id)
        return entries
    return [
        entry.model_copy(update={"vocabulary": [], "vocabulary_note": _RE_SHEET_NOTE})
        if entry.vocabulary_total
        else entry
        for entry in entries
    ]
