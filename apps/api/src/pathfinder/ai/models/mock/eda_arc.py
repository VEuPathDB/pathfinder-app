"""The EDA arcs: a two-group comparison on a study this site publishes, exported
as a step, and the study another site publishes, which the Lead declines.

Every study, entity, variable and group label is read from the tool returns,
the calls the arc made, and the filter sheet the Lead's instructions pin.
"""

from __future__ import annotations

from dataclasses import dataclass

from assistant_core.models.scripted import (
    called_tool_parts,
    scripted_call,
)
from pydantic import Field, TypeAdapter
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.arc import Script, history_free
from pathfinder.ai.models.mock.calls import classify, lead_final
from pathfinder.ai.models.mock.lead_flow import classified_this_turn
from pathfinder.ai.models.mock.message_words import message
from pathfinder.ai.models.mock.reads import (
    ToolAnswer,
    instructions_of,
    last_return,
    refusal_of,
    returns_of,
    text_return,
)
from pathfinder.domain.eda_parts import EdaFilterSheetEntry

_GENE_ID = "VEUPATHDB_GENE_ID"
# The measurement columns a comparison reads: counts take DESeq, arrays limma.
_COUNTS = ("SEQUENCE_READ_COUNT_SENSE", "SEQUENCE_READ_COUNT")
_ARRAYS = ("NORMALIZED_EXPRESSION", "NORMALIZED_INTENSITY")
_SHEET_HEAD = "### filter sheet for "
_SHEET = TypeAdapter(list[EdaFilterSheetEntry])
_FILTERS = "set_eda_filters"
_TWO_GROUPS = 2
_COMPARED_PROSE = "I compared the two groups of the study."
_EXPORTED_PROSE = (
    "I compared the two groups of the study and added the genes that differ "
    "between them as a step."
)
_NO_STUDY = "No study this site publishes matches the request."
_NO_GROUPS = "The study holds no sample variable with two groups to compare."
_ALL_HERE = "Every study the search found is published on this site."


class _Card(ToolAnswer):
    dataset_id: str
    not_here: str | None = None


class _Found(ToolAnswer):
    studies: list[_Card] = Field(default_factory=list)


class _Entity(ToolAnswer):
    entity_id: str
    parent_entity_id: str | None = None


class _Variable(ToolAnswer):
    variable_id: str


class _Described(ToolAnswer):
    entities: list[_Entity] = Field(default_factory=list)
    variables: list[_Variable] = Field(default_factory=list)
    gene_entity_id: str | None = None

    def ancestors(self) -> list[str]:
        """The entities above the gene entity, nearest first."""
        parents = {e.entity_id: e.parent_entity_id for e in self.entities}
        chain: list[str] = []
        at = parents.get(self.gene_entity_id or "")
        while at is not None:
            chain.append(at)
            at = parents.get(at)
        return chain

    def value_variable(self) -> tuple[str, str]:
        """The measurement column this entity holds, and the method it takes."""
        held = {v.variable_id for v in self.variables}
        counted = [v for v in _COUNTS if v in held]
        arrays = [v for v in _ARRAYS if v in held]
        if not counted and arrays:
            return arrays[0], "limma"
        return (counted or list(_COUNTS))[0], "DESeq"


class _Filtered(ToolAnswer):
    applied: bool = False
    sheet_pinned: bool = False


class _Filter(ToolAnswer):
    entity_id: str
    variable_id: str
    string_set: list[str] = Field(default_factory=list)


class _FilterCall(ToolAnswer):
    filters: list[_Filter] = Field(default_factory=list)


def _studies(messages: list[ModelMessage]) -> list[_Card] | None:
    found = last_return(messages, "search_eda_studies", _Found)
    return None if found is None else found.studies


def _search() -> ToolCallPart:
    return scripted_call("search_eda_studies", {"query": message()})


def _groups(
    messages: list[ModelMessage], samples: list[str]
) -> EdaFilterSheetEntry | None:
    """The first single-valued string variable of a sample entity with two values."""
    lines = instructions_of(messages).splitlines()
    heads = [i for i, line in enumerate(lines) if line.startswith(_SHEET_HEAD)]
    if not heads or heads[-1] + 1 >= len(lines):
        return None
    return next(
        (
            e
            for e in _SHEET.validate_json(lines[heads[-1] + 1])
            if e.entity_id in samples
            and e.filter_type == "stringSet"
            and not e.is_multi_valued
            and len(e.vocabulary) >= _TWO_GROUPS
        ),
        None,
    )


def _applied(messages: list[ModelMessage]) -> _Filter | None:
    """The filter the arc applied: the comparator and its two labels."""
    for part in reversed(called_tool_parts(messages)):
        if part.tool_name == _FILTERS:
            call = _FilterCall.model_validate(part.args_as_dict())
            if call.filters:
                return call.filters[0]
    return None


def _filter(dataset: str, groups: EdaFilterSheetEntry) -> ToolCallPart:
    chosen = {
        "entityId": groups.entity_id,
        "variableId": groups.variable_id,
        "type": "stringSet",
        "stringSet": groups.vocabulary[:2],
    }
    return scripted_call(_FILTERS, {"dataset_id": dataset, "filters": [chosen]})


def _compute(gene: str, entity: _Described, chosen: _Filter) -> ToolCallPart:
    value, method = entity.value_variable()
    return scripted_call(
        "run_eda_compute",
        {
            "identifier_variable": {"entityId": gene, "variableId": _GENE_ID},
            "value_variable": {"entityId": gene, "variableId": value},
            "comparator_variable": {
                "entityId": chosen.entity_id,
                "variableId": chosen.variable_id,
            },
            "group_a_labels": chosen.string_set[:1],
            "group_b_labels": chosen.string_set[1:2],
            "method": method,
            "caption": "Genes that differ between the two sample groups",
        },
    )


def _after_the_filter(
    messages: list[ModelMessage], study: _Study, ending: Script
) -> ToolCallPart:
    chosen = _applied(messages)
    if chosen is None:
        return lead_final(_NO_GROUPS, "await_user")
    if text_return(messages, "preview_eda_subset") is None:
        return scripted_call("preview_eda_subset", {"entity_id": chosen.entity_id})
    if text_return(messages, "run_eda_compute") is None:
        return _compute(study.gene, study.entity, chosen)
    return ending(messages)


def _compared() -> ToolCallPart:
    """End on the comparison, exporting nothing."""
    return lead_final(_COMPARED_PROSE, "await_user")


def _exported(messages: list[ModelMessage]) -> ToolCallPart:
    """Export the compared genes as a step and check it."""
    if text_return(messages, "create_eda_step") is None:
        return scripted_call(
            "create_eda_step",
            {"effect_size_threshold": 1.0, "significance_threshold": 0.05},
        )
    if text_return(messages, "verify_strategy") is None:
        return scripted_call("verify_strategy", {"reason": "check the exported step"})
    return lead_final(_EXPORTED_PROSE, "complete", strategy_changed=True)


@dataclass(frozen=True)
class _Study:
    """The study the arc compares on, read from its search and its two reads."""

    dataset: str
    tree: _Described
    entity: _Described

    @property
    def gene(self) -> str:
        return self.tree.gene_entity_id or ""


def _here(messages: list[ModelMessage]) -> _Card | None:
    return next((s for s in _studies(messages) or [] if s.not_here is None), None)


def _study(messages: list[ModelMessage]) -> _Study | None:
    """The study once its search, its entity tree and its gene entity are read."""
    here = _here(messages)
    described = returns_of(messages, "describe_eda_study", _Described)
    tree = next((d for d in described if d.entities), None)
    entity = next((d for d in described if d.variables), None)
    if here is None or tree is None or entity is None:
        return None
    return _Study(dataset=here.dataset_id, tree=tree, entity=entity)


def _next_read(messages: list[ModelMessage]) -> ToolCallPart:
    """The search or the study read that comes next."""
    if _studies(messages) is None:
        return _search()
    here = _here(messages)
    if here is None:
        return lead_final(_NO_STUDY, "await_user")
    described = returns_of(messages, "describe_eda_study", _Described)
    tree = next((d for d in described if d.entities), None)
    if tree is None:
        return scripted_call("describe_eda_study", {"dataset_id": here.dataset_id})
    return scripted_call(
        "describe_eda_study",
        {"dataset_id": here.dataset_id, "entity_id": tree.gene_entity_id or ""},
    )


def _analysis_call(
    messages: list[ModelMessage], study: _Study, ending: Script
) -> ToolCallPart:
    """Open the analysis, read its sheet, filter two groups, then compare them."""
    if text_return(messages, "open_eda_analysis") is None:
        return scripted_call(
            "open_eda_analysis",
            {"dataset_id": study.dataset, "purpose": "Two-group comparison"},
        )
    filtered = returns_of(messages, _FILTERS, _Filtered)
    if not any(f.sheet_pinned for f in filtered):
        return scripted_call(_FILTERS, {"dataset_id": study.dataset})
    if any(f.applied for f in filtered):
        return _after_the_filter(messages, study, ending)
    groups = _groups(messages, study.tree.ancestors())
    if groups is None:
        return lead_final(_NO_GROUPS, "await_user")
    return _filter(study.dataset, groups)


def _comparison(ending: Script) -> Script:
    """Find a study, read it, filter two groups, compare them, then end."""

    def script(messages: list[ModelMessage]) -> ToolCallPart:
        if not classified_this_turn(messages):
            return classify("new_strategy")
        study = _study(messages)
        if study is None:
            return _next_read(messages)
        return _analysis_call(messages, study, ending)

    return script


eda_compare = _comparison(_exported)
eda_compare_no_step = _comparison(history_free(_compared))


def eda_other_site(messages: list[ModelMessage]) -> ToolCallPart:
    """Open the study another site publishes and give its refusal as the reply."""
    if not classified_this_turn(messages):
        return classify("new_strategy")
    studies = _studies(messages)
    if studies is None:
        return _search()
    elsewhere = next((s for s in studies if s.not_here is not None), None)
    if elsewhere is None:
        return lead_final(_ALL_HERE, "await_user")
    refused = refusal_of(messages, "open_eda_analysis")
    if refused is None:
        return scripted_call(
            "open_eda_analysis",
            {
                "dataset_id": elsewhere.dataset_id,
                "purpose": "Study another site publishes",
            },
        )
    return lead_final(elsewhere.not_here or refused, "await_user")
