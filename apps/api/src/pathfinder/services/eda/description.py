"""How a study is described. One derivation, read by the agent's tools."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import BaseModel, ConfigDict, Field, field_validator
from veupathdb.domain import (
    VEUPATHDB_GENE_ID,
    EntityFacts,
    entity_by_id,
    find_gene_entity,
    variable_by_id,
    walk_entities,
)
from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaPermissionEntry,
    EdaStudyDetail,
    EdaVariableSpec,
    differential_expression_computations,
)

from pathfinder.domain.eda_parts import EdaComputeSummary, EdaFilterType
from pathfinder.platform.errors import NotFoundError

_VOCABULARY_SHOWN = 40
_CONTINUOUS = "continuous"
_MULTIFILTER_DISPLAY = "multifilter"
_DATE_TIME_MARKER = "T"


class UnknownEdaEntityError(NotFoundError):
    """The study declares no entity by that id."""

    def __init__(self, study_id: str, entity_id: str, known: Sequence[str]) -> None:
        self.entity_id = entity_id
        self.guidance = (
            f"Study {study_id} declares no entity {entity_id!r}. Its entities "
            f"are {list(known)}."
        )
        super().__init__(title="The study has no such entity", detail=self.guidance)


class EdaVariableOut(CamelModel):
    """One filterable variable, with the exact filter type it takes."""

    entity_id: str
    variable_id: str
    display_name: str
    variable_type: str
    filter_type: EdaFilterType | None = None
    data_shape: str | None = None
    is_multi_valued: bool = False
    vocabulary: list[str] = Field(default_factory=list)
    vocabulary_total: int = 0
    vocabulary_note: str | None = None
    range_min: float | None = None
    range_max: float | None = None
    date_min: str | None = None
    date_max: str | None = None
    sub_filter_variable_ids: list[str] = Field(default_factory=list)
    hide_from: list[str] = Field(default_factory=list)


class EdaEntityOut(CamelModel):
    entity_id: str
    display_name: str
    display_name_plural: str = ""
    parent_entity_id: str | None = None
    variable_count: int = 0
    has_gene_id: bool = False


class StudyDescription(CamelModel):
    """A study's shape, as the agent's tools read it."""

    dataset_id: str
    study_id: str
    display_name: str = ""
    entities: list[EdaEntityOut] = Field(default_factory=list)
    variables: list[EdaVariableOut] = Field(default_factory=list)
    gene_entity_id: str | None = None
    gene_entity_problem: str | None = None
    can_subset: bool = False
    can_export_rows: bool = False


class _Bounds(BaseModel):
    """A variable's declared bounds. Numbers on a number, strings on a date."""

    model_config = ConfigDict(extra="ignore", from_attributes=True)

    range_min: float | str | None = None
    range_max: float | str | None = None


class EdaVariableFacts(BaseModel):
    """What a variable declares, whatever concrete wire type carries it.

    A category variable declares no vocabulary and no bounds, so every field
    beyond the identity has a default.
    """

    model_config = ConfigDict(extra="ignore", from_attributes=True)

    id: str
    type: str
    display_name: str = ""
    display_type: str = "default"
    data_shape: str | None = None
    is_multi_valued: bool = False
    vocabulary: list[str] = Field(default_factory=list)
    hide_from: list[str] = Field(default_factory=list)
    distribution_defaults: _Bounds = Field(default_factory=_Bounds)

    @field_validator("vocabulary", mode="before")
    @classmethod
    def _no_vocabulary_is_an_empty_one(cls, value: object) -> object:
        return [] if value is None else value


class _Authorization(BaseModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    subsetting: bool = False
    results_all: bool = False


class EdaPermissionFacts(BaseModel):
    """What this account may do with a dataset, and what the dataset is called."""

    model_config = ConfigDict(extra="ignore", from_attributes=True)

    study_id: str
    display_name: str = ""
    action_authorization: _Authorization = Field(default_factory=_Authorization)

    @property
    def can_subset(self) -> bool:
        return self.action_authorization.subsetting

    @property
    def can_export_rows(self) -> bool:
        return self.action_authorization.results_all


def permission_facts(entry: EdaPermissionEntry) -> EdaPermissionFacts:
    """Read one permission entry as the answers a description needs."""
    return EdaPermissionFacts.model_validate(entry, from_attributes=True)


class EdaEntityFacts(BaseModel):
    """What an entity declares, beyond the tree shape the domain walks."""

    model_config = ConfigDict(extra="ignore", from_attributes=True)

    id: str
    display_name: str = ""
    display_name_plural: str = ""


def entity_facts(entity: object) -> EdaEntityFacts:
    """Read one wire entity as the names a description reports."""
    return EdaEntityFacts.model_validate(entity, from_attributes=True)


def variable_facts(variable: object) -> EdaVariableFacts:
    """Read one wire variable as the facts every filter type needs."""
    return EdaVariableFacts.model_validate(variable, from_attributes=True)


def variable_at(
    study: EdaStudyDetail,
    entity_id: str,
    variable_id: str | None,
) -> EdaVariableFacts | None:
    """One variable as the study declares it, or None when it declares none."""
    if variable_id is None:
        return None
    entity = entity_by_id(study.root_entity, entity_id)
    if entity is None:
        return None
    variable = variable_by_id(entity, variable_id)
    return None if variable is None else variable_facts(variable)


def display_names(study: EdaStudyDetail) -> dict[tuple[str, str], str]:
    """Every variable's display name, keyed by the pair that names it."""
    return {
        (entity.id, variable.id): variable_facts(variable).display_name
        for entity in walk_entities(study.root_entity)
        for variable in entity.variables
    }


def _filter_type_of(facts: EdaVariableFacts) -> EdaFilterType | None:
    """The one filter type this variable takes, or None when it takes none."""
    match facts.type:
        case "string":
            return "stringSet"
        case "number" | "integer":
            return "numberRange" if facts.data_shape == _CONTINUOUS else "numberSet"
        case "date":
            return "dateRange" if facts.data_shape == _CONTINUOUS else "dateSet"
        case "longitude":
            return "longitudeRange"
        case "category":
            return "multiFilter" if facts.display_type == _MULTIFILTER_DISPLAY else None
        case _:
            return None


def with_time_part(bound: str) -> str:
    """A date bound the service accepts. A bare date is a server error."""
    return bound if _DATE_TIME_MARKER in bound else f"{bound}T00:00:00"


def _number_bound(value: float | str | None) -> float | None:
    match value:
        case int() | float():
            return float(value)
        case _:
            return None


def _date_bound(value: float | str | None) -> str | None:
    match value:
        case str():
            return with_time_part(value)
        case _:
            return None


def vocabulary_note(*, total: int, shown: int) -> str | None:
    """What a cut vocabulary says about the values it does not carry."""
    if total <= shown:
        return None
    return (
        f"{total} values in all; the first {shown} are shown. Ask "
        f"preview_eda_subset for this variable's distribution to see which "
        f"values the current subset holds."
    )


def variable_out(
    *,
    entity_id: str,
    facts: EdaVariableFacts,
    sub_filter_variable_ids: list[str],
) -> EdaVariableOut | None:
    """One filterable variable as the model reads it, or None when it is not one."""
    filter_type = _filter_type_of(facts)
    if filter_type is None:
        return None
    total = len(facts.vocabulary)
    shown = facts.vocabulary[:_VOCABULARY_SHOWN]
    note = vocabulary_note(total=total, shown=len(shown))
    bounds = facts.distribution_defaults
    return EdaVariableOut(
        entity_id=entity_id,
        variable_id=facts.id,
        display_name=facts.display_name,
        variable_type=facts.type,
        filter_type=filter_type,
        data_shape=facts.data_shape,
        is_multi_valued=facts.is_multi_valued,
        vocabulary=shown,
        vocabulary_total=total,
        vocabulary_note=note,
        range_min=_number_bound(bounds.range_min),
        range_max=_number_bound(bounds.range_max),
        date_min=_date_bound(bounds.range_min),
        date_max=_date_bound(bounds.range_max),
        sub_filter_variable_ids=sub_filter_variable_ids,
        hide_from=facts.hide_from,
    )


def children_of(entity: EntityFacts, variable_id: str) -> list[str]:
    """The sub-filter variables one category variable declares."""
    return [
        variable.id
        for variable in entity.variables
        if variable.parent_id == variable_id
    ]


def entity_cards(study: EdaStudyDetail) -> list[EdaEntityOut]:
    """Every entity of the tree, with its parent and its variable count."""
    parents = {
        child.id: entity.id
        for entity in walk_entities(study.root_entity)
        for child in entity.children
    }
    return [
        EdaEntityOut(
            entity_id=entity.id,
            display_name=entity_facts(entity).display_name,
            display_name_plural=entity_facts(entity).display_name_plural,
            parent_entity_id=parents.get(entity.id),
            variable_count=len(entity.variables),
            has_gene_id=variable_by_id(entity, VEUPATHDB_GENE_ID) is not None,
        )
        for entity in walk_entities(study.root_entity)
    ]


def _variable_cards(entity: EntityFacts) -> list[EdaVariableOut]:
    return [
        described
        for described in (
            variable_out(
                entity_id=entity.id,
                facts=variable_facts(variable),
                sub_filter_variable_ids=children_of(entity, variable.id),
            )
            for variable in entity.variables
        )
        if described is not None
    ]


def variable_cards(
    study: EdaStudyDetail, entity_id: str | None
) -> list[EdaVariableOut]:
    """One entity's filterable variables, or the whole study's when none is named."""
    if entity_id is None:
        return [
            card
            for entity in walk_entities(study.root_entity)
            for card in _variable_cards(entity)
        ]
    entity = entity_by_id(study.root_entity, entity_id)
    if entity is None:
        known = [known.id for known in walk_entities(study.root_entity)]
        raise UnknownEdaEntityError(study.id, entity_id, known)
    return _variable_cards(entity)


def describe_study(
    entry: EdaPermissionFacts,
    study: EdaStudyDetail,
    *,
    dataset_id: str,
    entity_id: str | None = None,
) -> StudyDescription:
    """The study's entity tree and its filterable variables, derived once."""
    gene = find_gene_entity(study, subject="strategy step")
    return StudyDescription(
        dataset_id=dataset_id,
        study_id=study.id,
        display_name=entry.display_name,
        entities=entity_cards(study),
        variables=variable_cards(study, entity_id),
        gene_entity_id=gene.entity_id,
        gene_entity_problem=gene.error,
        can_subset=entry.can_subset,
        can_export_rows=entry.can_export_rows,
    )


class _SubFilterFacts(BaseModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    variable_id: str
    string_set: list[str] = Field(default_factory=list)


class EdaFilterFacts(BaseModel):
    """One wire filter, read for the sentence that describes it."""

    model_config = ConfigDict(extra="ignore", from_attributes=True)

    entity_id: str
    variable_id: str
    type: str
    string_set: list[str] = Field(default_factory=list)
    number_set: list[float] = Field(default_factory=list)
    date_set: list[str] = Field(default_factory=list)
    min: float | str | None = None
    max: float | str | None = None
    left: float | None = None
    right: float | None = None
    operation: str = ""
    sub_filters: list[_SubFilterFacts] = Field(default_factory=list)


def _one_of(name: str, values: Sequence[object]) -> str:
    return f"{name} is one of {', '.join(str(value) for value in values)}"


def _members(facts: EdaFilterFacts) -> Sequence[object]:
    match facts.type:
        case "stringSet":
            return facts.string_set
        case "numberSet":
            return facts.number_set
        case _:
            return facts.date_set


def _summary(facts: EdaFilterFacts, name: str) -> str:
    match facts.type:
        case "stringSet" | "numberSet" | "dateSet":
            return _one_of(name, _members(facts))
        case "numberRange" | "dateRange":
            return f"{name} is between {facts.min} and {facts.max}"
        case "longitudeRange":
            return f"{name} is between longitude {facts.left} and {facts.right}"
        case "multiFilter":
            children = ", ".join(sub.variable_id for sub in facts.sub_filters)
            return f"{name} matches the {facts.operation} of {children}"
        case _:
            return f"{name} is filtered by {facts.type}"


def filter_summaries(
    filters: Sequence[object],
    *,
    display_names: Mapping[tuple[str, str], str],
) -> list[str]:
    """One sentence per filter, for the researcher and for the model."""
    summaries: list[str] = []
    for entry in filters:
        facts = EdaFilterFacts.model_validate(entry, from_attributes=True)
        key = (facts.entity_id, facts.variable_id)
        summaries.append(_summary(facts, display_names.get(key, facts.variable_id)))
    return summaries


def compute_summary(
    descriptor: EdaAnalysisDescriptor,
    *,
    display_names: Mapping[tuple[str, str], str],
) -> EdaComputeSummary | None:
    """The analysis's comparison in the study's own words, or None when it has none."""
    computations = differential_expression_computations(descriptor)
    if not computations:
        return None
    config = computations[0].descriptor.configuration

    def named(spec: EdaVariableSpec) -> str:
        return display_names.get((spec.entity_id, spec.variable_id), spec.variable_id)

    return EdaComputeSummary(
        method=config.differential_expression_method,
        identifier_variable=named(config.identifier_variable),
        value_variable=named(config.value_variable),
        comparator_variable=named(config.comparator.variable),
        group_a=[group.label for group in config.comparator.group_a],
        group_b=[group.label for group in config.comparator.group_b],
    )
