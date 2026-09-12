from collections.abc import Collection
from dataclasses import dataclass, field

from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from veupathdb.domain.parameters import ParamValue, VocabOption
from veupathdb_mcp.catalog import SheetEntry

from pathfinder.domain.strategy.constraints import Constraint
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    DroppedCriterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
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


class PinnedSheet(BaseModel):
    """What FRAME holds open for one criterion until the criterion is decided.

    The model copies values out of it several calls after it opened, so it is
    rendered in the instructions rather than left in the tool return. It is the
    whole parameter sheet only when ``opened`` is true; otherwise it carries the
    vocabularies a dependent re-read produced, which name no template.
    """

    search_name: str
    opened: bool
    entries: list[SheetEntry] = Field(default_factory=list)
    # Params whose vocabulary changed once the parents were bound, in sheet order.
    redecide: list[str] = Field(default_factory=list)

    def params_template(self) -> dict[str, None]:
        return {entry.name: None for entry in self.entries}


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
    # The sheets open right now, by criterion, oldest first.
    open_sheets: dict[str, PinnedSheet] = field(default_factory=dict)

    def pin_sheet(
        self, criterion_id: str, search_name: str, entries: list[SheetEntry]
    ) -> PinnedSheet:
        """Open a sheet for the criterion, replacing anything it holds."""
        self.open_sheets.pop(criterion_id, None)
        sheet = PinnedSheet(search_name=search_name, opened=True, entries=entries)
        self.open_sheets[criterion_id] = sheet
        return sheet

    def pin_fresh_vocabularies(
        self, criterion_id: str, search_name: str, entries: list[SheetEntry]
    ) -> None:
        """Hold the vocabularies the bound parents produce, to decide again.

        They replace the entries the sheet was read under. A criterion that
        never opened a sheet holds these alone, and they are not one.
        """
        sheet = self.open_sheets.get(criterion_id)
        if sheet is None or sheet.search_name != search_name:
            sheet = PinnedSheet(search_name=search_name, opened=False)
            self.open_sheets.pop(criterion_id, None)
            self.open_sheets[criterion_id] = sheet
        fresh = {entry.name: entry for entry in entries}
        kept = [fresh.get(entry.name, entry) for entry in sheet.entries]
        added = [entry for entry in entries if entry.name not in {e.name for e in kept}]
        sheet.entries = [*kept, *added]
        sheet.redecide = [e.name for e in sheet.entries if e.name in fresh]

    def clear_redecide(self, criterion_id: str) -> None:
        """Stop asking for a fresh decision the criterion no longer owes."""
        sheet = self.open_sheets.get(criterion_id)
        if sheet is not None:
            sheet.redecide = []

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
        self.open_sheets.pop(criterion.id, None)

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
        self.open_sheets.pop(criterion_id, None)
        return True

    def drop_criteria_for_steps(self, step_ids: Collection[str]) -> None:
        """Forget the criteria the removed steps answered.

        A criterion the graph no longer holds addresses nothing, so the spec
        and the graph stay in one address space.
        """
        removed = set(step_ids)
        if not removed:
            return
        spec = self.operational_spec_draft
        spec.criteria = [c for c in spec.criteria if c.id not in removed]
        spec.open_slots = [s for s in spec.open_slots if s.criterion_id not in removed]
        if spec.structure is not None:
            pruned = _structure_without(spec.structure.root, removed)
            spec.structure = None if pruned is None else SpecStructure(root=pruned)

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


def _structure_without(node: StructureNode, removed: set[str]) -> StructureNode | None:
    """The structure node with the removed criteria taken out of it.

    A combine or transform whose every input is gone states nothing, so it
    goes with them.
    """
    if node.criterion_id is not None and node.criterion_id in removed:
        return None
    inputs = [
        kept
        for kept in (_structure_without(child, removed) for child in node.inputs)
        if kept is not None
    ]
    if node.kind != "leaf" and not inputs:
        return None
    return node.model_copy(update={"inputs": inputs})
