from dataclasses import dataclass, field

from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from veupathdb.domain.parameters.values import ParamValue
from veupathdb.domain.parameters.wdk_vocab import VocabOption
from veupathdb.domain.strategy.constraints import Constraint
from veupathdb.domain.strategy.operational_spec import (
    Criterion,
    DroppedCriterion,
    OperationalSpec,
    SpecStructure,
)


class ParamVocabSnapshot(BaseModel):
    """A projection of ``ParameterInfo``, captured during discovery.

    It carries a flat list of enum entries (``allowed_values``) OR a rendered
    tree string (``allowed_values_tree``) for a multi-pick vocabulary.
    Planning commits values from this snapshot verbatim and invents none.
    """

    model_config = ConfigDict(extra="ignore", validate_by_name=True)

    # The library calls the field ``type``; the prompts read ``param_type``.
    param_type: str = Field(validation_alias=AliasChoices("param_type", "type"))
    required: bool
    help: str = ""
    default_value: str | None = None
    allowed_values: list[VocabOption] | None = None
    allowed_values_tree: str | None = None


class SearchOverview(BaseModel):
    search_name: str
    display_name: str
    record_type: str
    description: str
    parameter_names: list[str]
    required_params: list[str]

    param_vocab: dict[str, ParamVocabSnapshot] = Field(default_factory=dict)


@dataclass
class AgentToolState:
    discovered_searches: dict[str, SearchOverview] = field(default_factory=dict)
    catalog_search_names: set[str] = field(default_factory=set)
    read_param_options: set[str] = field(default_factory=set)
    operational_spec_draft: OperationalSpec = field(default_factory=OperationalSpec)
    # The organisms this investigation states. A capped vocabulary renders the
    # branches that match them first.
    organism_hints: list[str] = field(default_factory=list)
    # How the user said their evidence lines combine. A proposed structure that
    # contradicts one of them is refused.
    combination_requirements: list[Constraint] = field(default_factory=list)
    # Params already handed back for a fresh decision, by criterion and search.
    # Searches share parameter names, so the search is part of the key.
    redecided_params: set[tuple[str, str, str]] = field(default_factory=set)
    # Criterion and search pairs already sent a full parameter sheet.
    sheeted_criteria: set[tuple[str, str]] = field(default_factory=set)

    def mark_sheet_shown(self, criterion_id: str, search_name: str) -> None:
        self.sheeted_criteria.add((criterion_id, search_name))

    def was_sheet_shown(self, criterion_id: str, search_name: str) -> bool:
        """Whether the vocabularies for this pair were already sent this turn.

        A second sheet repeats them at full size, so it is sent without them.
        """
        return (criterion_id, search_name) in self.sheeted_criteria

    def mark_redecided(
        self, criterion_id: str, search_name: str, param_name: str
    ) -> None:
        self.redecided_params.add((criterion_id, search_name, param_name))

    def was_redecided(
        self, criterion_id: str, search_name: str, param_name: str
    ) -> bool:
        """Whether this param's fresh vocabulary was already shown here.

        The proposal that follows is a decision under that vocabulary, so it binds
        rather than asking again.
        """
        return (criterion_id, search_name, param_name) in self.redecided_params

    def frame_set_criterion(self, criterion: Criterion) -> None:
        spec = self.operational_spec_draft
        spec.criteria = [c for c in spec.criteria if c.id != criterion.id]
        spec.criteria.append(criterion)

    def frame_set_structure(self, structure: SpecStructure) -> None:
        self.operational_spec_draft.structure = structure

    def frame_drop_criterion(self, criterion_id: str, reason: str) -> bool:
        """Remove a criterion from the draft (keyed by id, like
        ``frame_set_criterion``) and record it in ``dropped``. Returns False if
        no criterion has that id — so a dropped criterion's open params can no
        longer keep ``ready_to_build`` False. Returns True when one was removed."""
        spec = self.operational_spec_draft
        match = next((c for c in spec.criteria if c.id == criterion_id), None)
        if match is None:
            return False
        spec.criteria = [c for c in spec.criteria if c.id != criterion_id]
        spec.dropped.append(DroppedCriterion(text=match.text, reason=reason))
        return True

    def resolved_params_for(self, search_name: str) -> dict[str, ParamValue]:
        """Params the draft spec has already bound on ``search_name``.

        A dependent vocabulary is only valid under its parent values, and WDK
        answers with the search defaults when no context is supplied.
        """
        if not search_name:
            return {}
        merged: dict[str, ParamValue] = {}
        for criterion in self.operational_spec_draft.criteria:
            if criterion.search_name == search_name:
                merged.update(criterion.resolved_params)
        return merged

    @staticmethod
    def param_read_key(
        search_name: str,
        parameter_id: str,
        *,
        context_values: dict[str, ParamValue] | None = None,
        query: str | None = None,
    ) -> str:
        """Stable key for one parameter-options read. Context-sensitive so a
        dependent param re-read under a different parent value is a new read,
        not a dedup hit."""
        ctx = ""
        if context_values:
            ctx = ";".join(
                f"{k}={v.model_dump_json()}" for k, v in sorted(context_values.items())
            )
        return f"{search_name}|{parameter_id}|{ctx}|{query or ''}"

    def mark_param_read(self, key: str) -> None:
        self.read_param_options.add(key)

    def was_param_read(self, key: str) -> bool:
        return key in self.read_param_options

    def register_search(self, name: str, overview: SearchOverview) -> None:
        self.discovered_searches[name] = overview

    def get_overview(self, name: str) -> SearchOverview | None:
        return self.discovered_searches.get(name)

    def discovered_search_names(self) -> set[str]:
        return set(self.discovered_searches)

    def record_catalog_searches(self, names: list[str]) -> None:
        """Record search names returned by the catalog (search_for_searches /
        list_searches) so ``get_search_overview`` can be constrained to names
        the model has actually seen — never invented ones."""
        self.catalog_search_names.update(n for n in names if n)

    def candidate_search_names(self) -> set[str]:
        """Inspectable searches: catalog results plus already-inspected ones
        (re-inspection must not be masked)."""
        return self.catalog_search_names | set(self.discovered_searches)
