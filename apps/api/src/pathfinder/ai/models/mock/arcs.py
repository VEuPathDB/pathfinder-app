"""The Lead's arcs in the deterministic test model.

The Lead routes on the latest user message (plus consult-resume state) and
drives a scripted FRAME -> BUILD -> VERIFY flow; a build the thread refuses
ends the turn instead of verifying. The role table that picks this script,
and the sub-agent scripts, live in ``mock``; the arcs that only answer in prose
live in ``prose_arcs``, the canned FRAME specs in ``specs`` and the arguments
the calls carry in ``arc_args``.
"""

from __future__ import annotations

from assistant_core.models.scripted import (
    called_tool_parts,
    current_turn,
    deferred_tool_resolved,
    has_any,
    joined_user_text,
    last_user_text,
    next_unmade_call,
    retry_prompt_parts,
    scripted_call,
    tool_return_parts,
)
from pydantic import BaseModel, ConfigDict
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolCallPart

from pathfinder.ai.models.mock.arc_args import (
    attached_gene_list,
    consult_args,
    variant_args,
)
from pathfinder.ai.models.mock.prose_arcs import (
    CLARIFY_MARKERS,
    CLASSIFY,
    LeadTurnState,
    classify,
    lead_final,
    prose_only_sequence,
)
from pathfinder.ai.models.mock.specs import (
    SpecPlan,
    combined_spec,
    go_spec,
    interpro_spec,
    organism_for,
    single_spec,
)

SUCCESS_PROSE = (
    "**Verified end-to-end.** The strategy framed, built, and verified "
    "cleanly: root size looks right and the leaves are non-empty."
)
FEEDBACK_PROSE = (
    "**Verification found a problem.** One leaf **returned 0** rows, so the "
    "combined result is empty; that pattern is too narrow. Loosen it and I "
    "will re-verify."
)
_VARIANT_PROSE = (
    "I ran both search variants and compared their result sets above. Tell me "
    "which direction you'd like to carry into the strategy."
)
_SAVE_GENE_SET_PROSE = (
    "Saved to your workbench as a gene set. Enrichment, export and the "
    "control tools can read it from there."
)
_ENRICHMENT_PROSE = (
    "Enrichment is running on that gene set. I will summarize the ranked "
    "terms when it reports."
)
_EXPORT_PROSE = "The file is ready. Download it here: "
_CONTROLS_PROSE = (
    "I've saved your uploaded gene IDs as a control set. We can now score "
    "search variants against them whenever you're ready."
)
_LOOP_PROSE = (
    "I kept re-reading the same catalog listing and made no progress, so I "
    "stopped there."
)
_BUILD_REFUSED_PROSE = (
    "**Nothing was built.** This thread already has a strategy, and "
    "build_strategy refuses to replace one: every step id would change. Tell "
    "me what to change and I will call edit_strategy on the steps you name, "
    "or say to start over and I will clear the strategy first."
)
_EDIT_PROSE = (
    "**Substituted the organism** on the seed criterion. Every other criterion "
    "is unchanged, and the steps behind them keep the ids they had."
)
_REMEMBER_PROSE = (
    "Stored for future sessions: your default organism. I built nothing - say "
    "the word and I will turn it into a strategy."
)
_RECALL_PROSE = "This thread already carries: "
_RECALL_NOTHING = "no ledger yet"

# Markers are deliberately specific to the journeys' turn prompts so generic
# biology prompts fall through to the plain echo.
_FIX_MARKERS = ("loosen", "%mamm", "fix the phylogenetic", "fix the pattern")
_BUILD_MARKERS = ("3d7", "trophozoite", "derisi", "create step", "create delegation")
# A kinase-broadening request builds the two-leaf spec and fails verification,
# so the turn carries the zero-result guidance the editor specs read.
_FEEDBACK_MARKERS = ("interpro", "pf00069", "ec 2.7")
_GO_MARKERS = ("go term strategy", "protein kinase go genes")
_COMBINED_MARKERS = ("comprehensive kinase strategy", "all parameter types")
_VARIANT_MARKERS = ("compare two search variants", "compare search variants")
_CONSULT_MARKERS = ("consult me before planning", "ask me design questions")
# The FRAME arc that asks for one catalog listing over and over, which is what
# the repetition guard exists to stop.
LOOP_MARKERS = ("read the catalog again and again",)
# An edit turn names a substitution and asks for the rest to stand.
_EDIT_MARKERS = ("keep the rest", "swap the organism", "substitute the organism")
# An imperative to run or add, including assent to an offer the assistant made
# and a retry after a failed task. Every one of them asks for a build.
_ASSENT_MARKERS = ("yes, rerun", "run the differential expression now")
# A request to store a preference. It asks for no strategy.
_REMEMBER_MARKERS = ("please remember", "remember for future sessions")
# A request to read the thread's own record back. The Lead answers from the
# Ledger, so a branch's inherited state is visible in the reply.
_RECALL_MARKERS = ("recap what i have asked",)
# A save of a gene list: the workbench tool, never the memory note.
_SAVE_GENE_SET_MARKERS = ("as a gene set",)
_SAVE_GENE_SET_IDS = ("PF3D7_0709000", "PF3D7_1133400")
# An export of a set that is already saved: the file tool, on its id.
_EXPORT_MARKERS = ("export the gene set",)
_EXPORT_GENE_SET_ID = "gs_mock_export"
# An outright request to tune a built step: the approval-gated durable sweep.
_SWEEP_MARKERS = ("tune the parameters of",)
_SWEEP_STEP_ID = 440230693
_SWEEP_POSITIVES = ("PF3D7_0102600",)
_SWEEP_BUDGET = 6
_SWEEP_PROSE = (
    "The sweep is running. I will report the winning setting and its score "
    "when it reports."
)
# An enrichment of a set that is already saved: the durable tool, on its id.
_ENRICHMENT_MARKERS = ("enrichment on the gene set",)
_ENRICHMENT_GENE_SET_ID = "gs_mock_enrichment"
_ENRICHMENT_TYPES = ("go_function", "go_process", "go_component")
_RECALL_SECTION = "frame"
LOOP_CALL_ARGS = {"record_type": "transcript"}

BUILD = "build_strategy"

# The substring of ``build_would_replace_the_strategy`` that names the refusal.
_BUILD_REFUSED_MARKER = "build_strategy replaces it"
# The precondition layer withholds the tool on a thread that has a strategy, so
# the turn can meet the same refusal as an absence.
_BUILD_ABSENT_MARKER = "Unknown tool name"
# The Lead's pinned spec, and the words it holds while nothing is framed.
_SPEC_PIN = "## Operational Spec"
_NOTHING_FRAMED = "Not framed yet."


def spec_for(text: str, site_id: str) -> SpecPlan:
    """The canned spec a request builds, on the vocabulary of its own site.

    The Lead and the FRAME sub-agent both route through here, so the prose and
    the criteria always describe the same strategy.
    """
    lowered = text.lower()
    organism = organism_for(site_id)
    if has_any(lowered, _FIX_MARKERS) or has_any(lowered, _FEEDBACK_MARKERS):
        return interpro_spec(organism)
    if has_any(lowered, _GO_MARKERS):
        return go_spec(organism)
    if has_any(lowered, _COMBINED_MARKERS):
        return combined_spec(organism)
    return single_spec(organism)


def verification_succeeds(text: str) -> bool:
    """A broadening request fails verification until a fix request follows it."""
    lowered = text.lower()
    if has_any(lowered, _FIX_MARKERS):
        return True
    return not has_any(lowered, _FEEDBACK_MARKERS + CLARIFY_MARKERS)


def classified_this_turn(messages: list[ModelMessage]) -> bool:
    return any(
        part.tool_name == CLASSIFY for part in called_tool_parts(current_turn(messages))
    )


def _build_head(classification: str) -> list[ToolCallPart]:
    return [
        classify(classification),
        scripted_call("frame_problem", {"reason": "mock frame"}),
        scripted_call(BUILD, {}),
    ]


def _build_sequence(
    prose: str,
    next_state: LeadTurnState,
    *,
    classification: str,
) -> list[ToolCallPart]:
    return [
        *_build_head(classification),
        scripted_call("verify_strategy", {"reason": "mock verification"}),
        lead_final(prose, next_state, strategy_changed=True),
    ]


def _refused_build_sequence(classification: str) -> list[ToolCallPart]:
    """The arc a build takes on a thread that already has a strategy.

    The refusal ends the turn: verifying an unchanged strategy reports a
    success the build never made.
    """
    return [
        *_build_head(classification),
        lead_final(_BUILD_REFUSED_PROSE, "await_user"),
    ]


def _build_refused(messages: list[ModelMessage]) -> bool:
    return any(
        part.tool_name == BUILD
        and has_any(
            part.model_response(),
            (_BUILD_REFUSED_MARKER, _BUILD_ABSENT_MARKER),
        )
        for part in retry_prompt_parts(current_turn(messages))
    )


def _build_classification(messages: list[ModelMessage]) -> str:
    """A build extends the draft the Lead's pinned spec states, else starts one."""
    requests = [msg for msg in messages if isinstance(msg, ModelRequest)]
    pinned = (requests[-1].instructions or "") if requests else ""
    framed = _SPEC_PIN in pinned and _NOTHING_FRAMED not in pinned
    return "extend_strategy" if framed else "new_strategy"


def _lead_sequence(messages: list[ModelMessage]) -> list[ToolCallPart]:
    raw = last_user_text(messages)
    if deferred_tool_resolved(messages, "consult_user"):
        return _build_branch(messages, raw, _build_classification(messages))
    if has_any(raw.lower(), _RECALL_MARKERS):
        return _recall_sequence(messages)
    attached = attached_gene_list(joined_user_text(messages))
    if attached is not None:
        return [
            classify("new_strategy"),
            scripted_call(
                "build_control_set",
                {
                    "name": attached.control_set_name,
                    "positive_ids": attached.gene_ids,
                },
            ),
            lead_final(_CONTROLS_PROSE, "await_user"),
        ]
    return _routed_sequence(messages, raw)


def _ledger_section_read(messages: list[ModelMessage]) -> str:
    for part in tool_return_parts(messages):
        if part.tool_name == "read_ledger_section":
            return str(part.content)
    return _RECALL_NOTHING


def _recall_sequence(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Read one Ledger section and answer with it, dispatching no sub-agent."""
    return [
        scripted_call("read_ledger_section", {"section": _RECALL_SECTION}),
        lead_final(f"{_RECALL_PROSE}{_ledger_section_read(messages)}", "await_user"),
    ]


class _ExportedFile(BaseModel):
    """The link one export answered with."""

    model_config = ConfigDict(extra="ignore")

    download_url: str = ""


def _exported_link(messages: list[ModelMessage]) -> str:
    """The link the export tool answered with, as the reply reports it."""
    for part in tool_return_parts(messages):
        if part.tool_name == "export_gene_set":
            read = _ExportedFile.model_validate(part.content, from_attributes=True)
            return read.download_url
    return ""


def _kept_sequence(
    messages: list[ModelMessage],
    lowered: str,
) -> list[ToolCallPart] | None:
    """The arcs that act on a set or a preference the user already keeps.

    Enrichment and export of a saved set are two of them: they ask for no
    strategy.
    """
    if has_any(lowered, _EXPORT_MARKERS):
        return [
            classify("follow_up_question"),
            scripted_call(
                "export_gene_set",
                {"gene_set_id": _EXPORT_GENE_SET_ID, "output_format": "csv"},
            ),
            lead_final(
                f"{_EXPORT_PROSE}{_exported_link(messages)}",
                "await_user",
            ),
        ]
    if has_any(lowered, _ENRICHMENT_MARKERS):
        return [
            classify("follow_up_question"),
            scripted_call(
                "run_gene_set_enrichment",
                {
                    "gene_set_id": _ENRICHMENT_GENE_SET_ID,
                    "enrichment_types": list(_ENRICHMENT_TYPES),
                },
            ),
            lead_final(
                _ENRICHMENT_PROSE,
                "await_user",
                analysed_gene_set_ids=[_ENRICHMENT_GENE_SET_ID],
            ),
        ]
    if has_any(lowered, _SWEEP_MARKERS):
        return [
            classify("follow_up_question"),
            scripted_call(
                "optimize_search_parameters",
                {
                    "wdk_step_id": _SWEEP_STEP_ID,
                    "positive_controls": list(_SWEEP_POSITIVES),
                    "budget": _SWEEP_BUDGET,
                },
            ),
            lead_final(_SWEEP_PROSE, "await_user"),
        ]
    if has_any(lowered, _SAVE_GENE_SET_MARKERS):
        return [
            classify("follow_up_question"),
            scripted_call(
                "create_workbench_gene_set",
                {
                    "name": "mock gene set",
                    "gene_ids": list(_SAVE_GENE_SET_IDS),
                },
            ),
            lead_final(_SAVE_GENE_SET_PROSE, "await_user"),
        ]
    if has_any(lowered, _REMEMBER_MARKERS):
        return [
            classify("memory_request"),
            scripted_call(
                "remember",
                {
                    "kind": "preference",
                    "name": "default organism",
                    "summary": "The user works with Plasmodium falciparum 3D7.",
                    "content": {"organism": "Plasmodium falciparum 3D7"},
                },
            ),
            lead_final(_REMEMBER_PROSE, "await_user"),
        ]
    return None


def _one_tool_sequence(
    messages: list[ModelMessage],
    lowered: str,
) -> list[ToolCallPart] | None:
    """The arcs that answer after a dispatch of their own, not the journey."""
    kept = _kept_sequence(messages, lowered)
    if kept is not None:
        return kept
    if has_any(lowered, _EDIT_MARKERS):
        return [
            classify("edit_strategy"),
            scripted_call("edit_strategy", {"reason": "mock edit: swap the organism"}),
            scripted_call(
                "verify_strategy", {"reason": "mock verification of an edit"}
            ),
            lead_final(_EDIT_PROSE, "await_user", strategy_changed=True),
        ]
    if has_any(lowered, LOOP_MARKERS):
        return [
            classify("new_strategy"),
            scripted_call("frame_problem", {"reason": "mock loop"}),
            lead_final(_LOOP_PROSE, "await_user"),
        ]
    if has_any(lowered, _VARIANT_MARKERS):
        return [
            classify("follow_up_question"),
            scripted_call("compare_search_variants", variant_args()),
            lead_final(_VARIANT_PROSE, "await_user"),
        ]
    if has_any(lowered, _CONSULT_MARKERS):
        return [
            classify("new_strategy"),
            scripted_call("consult_user", consult_args()),
        ]
    return None


def _routed_sequence(messages: list[ModelMessage], raw: str) -> list[ToolCallPart]:
    lowered = raw.lower()
    dispatched = _one_tool_sequence(messages, lowered)
    if dispatched is not None:
        return dispatched
    prose = prose_only_sequence(lowered)
    if prose is not None:
        return prose
    if has_any(lowered, _ASSENT_MARKERS):
        return _build_branch(messages, raw, "extend_strategy")
    build = (
        _FIX_MARKERS
        + _FEEDBACK_MARKERS
        + _GO_MARKERS
        + _BUILD_MARKERS
        + _COMBINED_MARKERS
    )
    if has_any(lowered, build):
        return _build_branch(messages, raw, _build_classification(messages))
    return [lead_final(f"[mock] {raw}", "await_user")]


def _build_branch(
    messages: list[ModelMessage], raw: str, classification: str
) -> list[ToolCallPart]:
    if _build_refused(messages):
        return _refused_build_sequence(classification)
    if verification_succeeds(raw):
        return _build_sequence(
            SUCCESS_PROSE,
            "complete",
            classification=classification,
        )
    return _build_sequence(
        FEEDBACK_PROSE,
        "await_user",
        classification=classification,
    )


def lead_script(messages: list[ModelMessage]) -> ToolCallPart:
    """The next call of this turn's arc.

    The classification is the turn's own: an arc that opens with it re-runs it
    on every turn, so the intent the Lead gates its tools on is never a
    previous turn's.
    """
    sequence = _lead_sequence(messages)
    if sequence[0].tool_name != CLASSIFY:
        return next_unmade_call(sequence, messages)
    if not classified_this_turn(messages):
        return sequence[0]
    return next_unmade_call(sequence[1:], messages)
