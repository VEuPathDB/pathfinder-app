"""What an arc reads back from the tool returns and the instructions of a run."""

from __future__ import annotations

from assistant_core.models.scripted import (
    current_turn,
    retry_prompt_parts,
    tool_return_parts,
)
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import AliasChoices, ConfigDict, Field
from pydantic_ai.messages import ModelMessage, ModelRequest


class ToolAnswer(CamelModel):
    """The fields of one tool answer an arc reads; the rest are ignored."""

    model_config = ConfigDict(extra="ignore", from_attributes=True)


def _compacted(content: object) -> bool:
    """A compacted answer is text that holds no field."""
    match content:
        case str():
            return True
        case _:
            return False


def returns_of[T: ToolAnswer](
    messages: list[ModelMessage], tool: str, shape: type[T]
) -> list[T]:
    """Every answer ``tool`` gave in the run, in ``shape``. An answer of
    another shape fails."""
    return [
        shape.model_validate(part.content)
        for part in tool_return_parts(messages)
        if part.tool_name == tool and not _compacted(part.content)
    ]


def last_answer(messages: list[ModelMessage], tool: str) -> object | None:
    """The newest answer ``tool`` gave that is not compacted text."""
    answers = [
        part.content
        for part in tool_return_parts(messages)
        if part.tool_name == tool and not _compacted(part.content)
    ]
    return answers[-1] if answers else None


def last_return[T: ToolAnswer](
    messages: list[ModelMessage], tool: str, shape: type[T]
) -> T | None:
    found = returns_of(messages, tool, shape)
    return found[-1] if found else None


def refusal_of(messages: list[ModelMessage], tool: str) -> str | None:
    """The newest refusal ``tool`` sent back this turn, as the model reads it."""
    refused = [
        p for p in retry_prompt_parts(current_turn(messages)) if p.tool_name == tool
    ]
    return refused[-1].model_response() if refused else None


def turn_start_instructions(messages: list[ModelMessage]) -> str:
    """The instructions pinned when the turn began, before any call it made."""
    return instructions_of(current_turn(messages)[:1])


def instructions_of(messages: list[ModelMessage]) -> str:
    """The instructions pinned on the newest request of the run."""
    requests = [msg for msg in messages if isinstance(msg, ModelRequest)]
    return (requests[-1].instructions or "") if requests else ""


class _Step(ToolAnswer):
    id: str
    wdk_step_id: int | None = None
    primary_input_step_id: str | None = None
    secondary_input_step_id: str | None = None


class _Strategy(ToolAnswer):
    steps: list[_Step] | None = None


def _root(messages: list[ModelMessage]) -> tuple[_Step | None, dict[str, _Step]]:
    read = last_return(messages, "get_strategy", _Strategy)
    steps = {s.id: s for s in (read.steps or [])} if read is not None else {}
    inputs = {s.primary_input_step_id for s in steps.values()} | {
        s.secondary_input_step_id for s in steps.values()
    }
    root = next((s for s in steps.values() if s.id not in inputs), None)
    return root, steps


def root_wdk_step_id(messages: list[ModelMessage]) -> int | None:
    """The WDK id of the strategy's root, from the newest ``get_strategy``."""
    root, _steps = _root(messages)
    return None if root is None else root.wdk_step_id


class _Node(ToolAnswer):
    wdk_step_id: int | None = None


class _Outcome(ToolAnswer):
    root_count: int | None = None
    node_results: list[_Node] = Field(default_factory=list)


class _Built(ToolAnswer):
    outcome: _Outcome = Field(default_factory=_Outcome)


def built_root_wdk_step_id(messages: list[ModelMessage]) -> int | None:
    """The root the newest build pushed. Its nodes list the root last."""
    built = last_return(messages, "build_strategy", _Built)
    if built is None or not built.outcome.node_results:
        return None
    return built.outcome.node_results[-1].wdk_step_id


class _Digest(ToolAnswer):
    success: bool = False
    prose: str = ""


class _Verified(ToolAnswer):
    digest: _Digest = Field(default_factory=_Digest)


def verification_prose(messages: list[ModelMessage]) -> str:
    """What the newest verification said it found, or nothing before one."""
    read = last_return(messages, "verify_strategy", _Verified)
    return "" if read is None else read.digest.prose


def verified(messages: list[ModelMessage]) -> bool:
    """Whether the newest verification of the run reported success."""
    read = last_return(messages, "verify_strategy", _Verified)
    return read is not None and read.digest.success


class _Created(ToolAnswer):
    id: str


class _SavedSet(ToolAnswer):
    gene_set_created: _Created


class _Counted(ToolAnswer):
    gene_count: int


class _SavedCount(ToolAnswer):
    gene_set_created: _Counted


def saved_gene_count(messages: list[ModelMessage]) -> int | None:
    """How many genes the set this run saved holds."""
    saved = last_return(messages, "save_gene_set", _SavedCount)
    return None if saved is None else saved.gene_set_created.gene_count


class _Listed(ToolAnswer):
    gene_sets: list[_Created] = Field(default_factory=list)


def gene_set_id(messages: list[ModelMessage]) -> str | None:
    """The set this run saved, else the first set the listing names."""
    saved = last_return(messages, "save_gene_set", _SavedSet)
    if saved is not None:
        return saved.gene_set_created.id
    listed = last_return(messages, "list_gene_sets", _Listed)
    return listed.gene_sets[0].id if listed is not None and listed.gene_sets else None


class _ControlSet(ToolAnswer):
    control_set_id: str


def control_set_id(messages: list[ModelMessage]) -> str | None:
    built = last_return(messages, "build_control_set", _ControlSet)
    return None if built is None else built.control_set_id


class _LiveStep(ToolAnswer):
    step_id: str = ""
    display_name: str = ""
    estimated_size: int | None = None
    search_name: str | None = None
    wdk_step_id: int | None = None
    is_root: bool = False


class _Live(ToolAnswer):
    root_count: int | None = None
    steps: list[_LiveStep] = Field(default_factory=list)


def live_step_id(messages: list[ModelMessage], search_name: str) -> str | None:
    """The id of the step that runs ``search_name``, from the newest live read."""
    read = last_return(messages, "get_live_strategy_state", _Live)
    steps = [] if read is None else read.steps
    return next((s.step_id for s in steps if s.search_name == search_name), None)


def live_root_wdk_step_id(messages: list[ModelMessage]) -> int | None:
    """The WDK id of the root the newest live read names, or None."""
    read = last_return(messages, "get_live_strategy_state", _Live)
    steps = [] if read is None else read.steps
    return next((s.wdk_step_id for s in steps if s.is_root), None)


def _count_sentence(count: int | None) -> str:
    if count is None:
        return "The site gives no count for the strategy now."
    return f"The strategy returns {count:,} genes."


def live_count_sentence(messages: list[ModelMessage]) -> str:
    """The root count the site answers now, as a reply states it."""
    read = last_return(messages, "get_live_strategy_state", _Live)
    return _count_sentence(None if read is None else read.root_count)


def built_count_sentence(messages: list[ModelMessage]) -> str:
    """The root count the newest build answered, as a reply states it."""
    built = last_return(messages, "build_strategy", _Built)
    return _count_sentence(None if built is None else built.outcome.root_count)


def empty_steps_sentence(messages: list[ModelMessage]) -> str:
    """Each step the newest live read counts 0 genes for, by its displayed name."""
    read = last_return(messages, "get_live_strategy_state", _Live)
    steps = [] if read is None else read.steps
    return " ".join(
        f"The step '{s.display_name}' returns 0 genes."
        for s in steps
        if s.estimated_size == 0
    )


class _Controls(ToolAnswer):
    positive_recovered_ids: list[str] | None = None
    positive_missed_ids: list[str] | None = None
    negative_admitted_ids: list[str] | None = None
    negative_excluded_ids: list[str] | None = None


class _Tested(ToolAnswer):
    """A test's outcome: a task's ``result``, or the ``outcome`` of a repeat."""

    result: _Controls = Field(
        default_factory=_Controls,
        validation_alias=AliasChoices("result", "outcome"),
    )


def controls_sentence(messages: list[ModelMessage]) -> str | None:
    """What the newest control test recovered and returned, or None before one."""
    tested = last_return(messages, "run_control_tests_on_step", _Tested)
    if tested is None:
        return None
    held = tested.result
    parts = []
    if held.positive_recovered_ids is not None and held.positive_missed_ids is not None:
        found = len(held.positive_recovered_ids)
        total = found + len(held.positive_missed_ids)
        parts.append(f"{found} of {total} positive controls recovered")
    if (
        held.negative_admitted_ids is not None
        and held.negative_excluded_ids is not None
    ):
        admitted = len(held.negative_admitted_ids)
        total = admitted + len(held.negative_excluded_ids)
        parts.append(f"{admitted} of {total} negative controls returned")
    return f"{'; '.join(parts)}." if parts else None


class _Reason(ToolAnswer):
    term: str = ""


class AddedSearchRead(ToolAnswer):
    """A step a write added: the search it runs and why it was chosen."""

    search_display_name: str
    rationale: _Reason | None = None


class _Wrote(ToolAnswer):
    added_searches: list[AddedSearchRead] = Field(default_factory=list)


def added_searches(messages: list[ModelMessage], tool: str) -> list[AddedSearchRead]:
    """The searches the newest answer of ``tool`` says it added."""
    wrote = last_return(messages, tool, _Wrote)
    return [] if wrote is None else wrote.added_searches


def added_search_lines(messages: list[ModelMessage]) -> str:
    """One list item per search this turn's build or edit added, its reason
    beside its name."""
    added = [
        *added_searches(messages, "build_strategy"),
        *added_searches(messages, "edit_strategy"),
    ]
    return "\n".join(
        f"- {a.search_display_name}"
        + ("" if a.rationale is None else f", chosen for {a.rationale.term}")
        for a in added
    )


class _Summary(ToolAnswer):
    summary: str = ""
    disposition: str = ""


def frame_is_ready(messages: list[ModelMessage]) -> bool:
    """Whether the newest frame pass answered with a spec ready to build."""
    read = last_return(messages, "frame_problem", _Summary)
    return read is not None and read.disposition == "spec_ready"


def frame_summary(messages: list[ModelMessage]) -> str:
    """What the newest frame or edit pass said it found."""
    reads = [
        read
        for tool in ("frame_problem", "edit_strategy")
        if (read := last_return(messages, tool, _Summary)) is not None
    ]
    return reads[-1].summary if reads else ""


class _Exported(ToolAnswer):
    download_url: str = ""


def exported_link(messages: list[ModelMessage]) -> str:
    read = last_return(messages, "export_gene_set", _Exported)
    return "" if read is None else read.download_url


class GeneRecord(ToolAnswer):
    gene_id: str
    organism: str = ""
    product: str = ""
    record_url: str = ""


def gene_records(messages: list[ModelMessage]) -> list[GeneRecord]:
    return returns_of(messages, "read_gene_record", GeneRecord)


class _Note(ToolAnswer):
    id: str


def note_id(messages: list[ModelMessage]) -> str | None:
    read = last_return(messages, "note", _Note)
    return None if read is None else read.id


def text_return(messages: list[ModelMessage], tool: str) -> str | None:
    """The newest answer of a tool that answers in text."""
    found = [str(p.content) for p in tool_return_parts(messages) if p.tool_name == tool]
    return found[-1] if found else None
