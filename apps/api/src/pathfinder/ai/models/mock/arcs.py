"""The Lead's arcs in the deterministic test model.

The Lead routes on the latest user message (plus consult-resume state) and
drives a scripted FRAME -> BUILD -> VERIFY flow; a build the thread refuses
ends the turn instead of verifying. The role table that picks this script,
and the sub-agent scripts, live in ``mock``; the canned FRAME specs live in
``specs``.
"""

from __future__ import annotations

from typing import Any, Literal

from assistant_core.models.scripted import (
    called_tool_parts,
    current_turn,
    current_user_text,
    deferred_tool_resolved,
    has_any,
    joined_user_text,
    last_user_text,
    next_unmade_call,
    retry_prompt_parts,
    scripted_call,
    terminal_call,
    tool_return_parts,
)
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.specs import (
    SpecPlan,
    combined_spec,
    go_spec,
    interpro_spec,
    organism_for,
    single_spec,
)

LeadTurnState = Literal["await_user", "complete"]

_CLARIFY_PROSE = (
    "Before I build this, let me **clarify** a few things so the strategy "
    "matches what you mean:\n\n"
    "- **Which** evidence defines 'expressed' — a mass-spec stage or a "
    "microarray percentile?\n"
    "- **How strict** on 'doesn't vary much' — what dN/dS cutoff?\n"
    "- What counts as 'no human equivalent' — which phylogenetic profile "
    "pattern?\n\n"
    "Answer those and I'll frame the strategy."
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
_IMPACT_PROSE = (
    "Switching the combine to INTERSECT makes the **operator** **stricter**: "
    "the result **drops** to genes supported by *both* signals. That tightens "
    "specificity at the cost of recall, so expect a smaller candidate list."
)
_VARIANT_PROSE = (
    "I ran both search variants and compared their result sets above. Tell me "
    "which direction you'd like to carry into the strategy."
)
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
_CONTEXT_PROSE = (
    "Good area to be in. I have not built anything yet. Want me to put a "
    "candidate strategy together for it?"
)
_RECALL_PROSE = "This thread already carries: "
_RECALL_NOTHING = "no ledger yet"

# Markers are deliberately specific to the journeys' turn prompts so generic
# biology prompts fall through to the plain echo.
_FIX_MARKERS = ("loosen", "%mamm", "fix the phylogenetic", "fix the pattern")
_IMPACT_MARKERS = ("switching the interpro", "switch the interpro", "interpro/go")
_BUILD_MARKERS = ("3d7", "trophozoite", "derisi", "create step", "create delegation")
# A kinase-broadening request builds the two-leaf spec and fails verification,
# so the turn carries the zero-result guidance the editor specs read.
_FEEDBACK_MARKERS = ("interpro", "pf00069", "ec 2.7")
_GO_MARKERS = ("go term strategy", "protein kinase go genes")
_COMBINED_MARKERS = ("comprehensive kinase strategy", "all parameter types")
_CLARIFY_MARKERS = ("human equivalent", "vary much")
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
# A request to store a preference, and a bare statement of what the user works
# on. Neither asks for a strategy.
_REMEMBER_MARKERS = ("please remember", "remember for future sessions")
_CONTEXT_MARKERS = ("i'm investigating", "i am investigating")
# A request to read the thread's own record back. The Lead answers from the
# Ledger, so a branch's inherited state is visible in the reply.
_RECALL_MARKERS = ("recap what i have asked",)
_RECALL_SECTION = "frame"
LOOP_CALL_ARGS = {"record_type": "transcript"}

CLASSIFY = "classify_user_intent"
BUILD = "build_strategy"

# The substring of ``build_would_replace_the_strategy`` that names the refusal.
_BUILD_REFUSED_MARKER = "build_strategy replaces it"
# The precondition layer withholds the tool on a thread that has a strategy, so
# the turn can meet the same refusal as an absence.
_BUILD_ABSENT_MARKER = "Unknown tool name"


def _variant_text_params(expression: str) -> dict[str, Any]:
    return {
        "text_expression": {"type": "string", "value": expression},
        "text_fields": {"type": "multi-pick-vocabulary", "values": ["product"]},
        "document_type": {"type": "string", "value": "gene"},
        "text_search_organism": {
            "type": "multi-pick-vocabulary",
            "values": ["Plasmodium falciparum 3D7"],
        },
    }


def _variant_args() -> dict[str, Any]:
    return {
        "variants": [
            {
                "label": "kinase",
                "search_name": "GenesByText",
                "record_type": "transcript",
                "parameters": _variant_text_params("kinase"),
            },
            {
                "label": "phosphatase",
                "search_name": "GenesByText",
                "record_type": "transcript",
                "parameters": _variant_text_params("phosphatase"),
            },
        ],
    }


def _consult_args() -> dict[str, Any]:
    return {
        "questions": [
            {
                "id": "q1",
                "prompt": "Fold-change threshold?",
                "kind": "single_choice",
                "options": [
                    {"label": "2-fold", "recommended": True},
                    {"label": "5-fold"},
                ],
            },
            {
                "id": "q2",
                "prompt": "Include the microarray arm?",
                "kind": "single_choice",
                "options": [{"label": "Yes"}, {"label": "No"}],
            },
        ],
    }


def _attachment_gene_ids(text: str) -> list[str]:
    """Pull the cleaned gene IDs the composer's attachment adapter inlined as
    ``Attached gene-ID list from <name>: ID, ID, ...`` (plain framing so the
    input injection scanner doesn't flag it)."""
    marker = text.find("Attached gene-ID list from")
    if marker == -1:
        return []
    colon = text.find(":", marker)
    if colon == -1:
        return []
    line = text[colon + 1 :].splitlines()[0]
    return [token.strip() for token in line.split(",") if token.strip()]


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
    return not has_any(lowered, _FEEDBACK_MARKERS + _CLARIFY_MARKERS)


def _lead_final(prose: str, next_state: LeadTurnState) -> ToolCallPart:
    return terminal_call({"prose": prose, "nextState": next_state})


def _classify(classification: str) -> ToolCallPart:
    return scripted_call(
        CLASSIFY,
        {
            "intent": {
                "rawText": current_user_text.get(),
                "classification": classification,
                "inferredGoal": f"[mock] {classification}",
            },
        },
    )


def _classified_this_turn(messages: list[ModelMessage]) -> bool:
    return any(
        part.tool_name == CLASSIFY for part in called_tool_parts(current_turn(messages))
    )


def _build_head(classification: str) -> list[ToolCallPart]:
    return [
        _classify(classification),
        scripted_call("frame_problem", {"reason": "mock frame"}),
        scripted_call(BUILD, {}),
    ]


def _build_sequence(
    prose: str,
    next_state: LeadTurnState,
    *,
    classification: str = "new_strategy",
) -> list[ToolCallPart]:
    return [
        *_build_head(classification),
        scripted_call("verify_strategy", {"reason": "mock verification"}),
        _lead_final(prose, next_state),
    ]


def _refused_build_sequence(classification: str) -> list[ToolCallPart]:
    """The arc a build takes on a thread that already has a strategy.

    The refusal ends the turn: verifying an unchanged strategy reports a
    success the build never made.
    """
    return [
        *_build_head(classification),
        _lead_final(_BUILD_REFUSED_PROSE, "await_user"),
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


def _lead_sequence(messages: list[ModelMessage]) -> list[ToolCallPart]:
    raw = last_user_text(messages)
    if deferred_tool_resolved(messages, "consult_user"):
        return _build_branch(messages, raw)
    if has_any(raw.lower(), _RECALL_MARKERS):
        return _recall_sequence(messages)
    ids = _attachment_gene_ids(joined_user_text(messages))
    if ids:
        return [
            _classify("new_strategy"),
            scripted_call(
                "build_control_set",
                {"name": "Uploaded controls", "positive_ids": ids},
            ),
            _lead_final(_CONTROLS_PROSE, "await_user"),
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
        _lead_final(f"{_RECALL_PROSE}{_ledger_section_read(messages)}", "await_user"),
    ]


def _prose_only_sequence(lowered: str) -> list[ToolCallPart] | None:
    """The arcs that answer in prose and call no tool."""
    if has_any(lowered, _IMPACT_MARKERS):
        return [_lead_final(_IMPACT_PROSE, "await_user")]
    if has_any(lowered, _CLARIFY_MARKERS):
        return [_lead_final(_CLARIFY_PROSE, "await_user")]
    if has_any(lowered, _CONTEXT_MARKERS):
        return [
            _classify("context_statement"),
            _lead_final(_CONTEXT_PROSE, "await_user"),
        ]
    return None


def _one_tool_sequence(lowered: str) -> list[ToolCallPart] | None:
    """The arcs that answer after a dispatch of their own, not the journey."""
    if has_any(lowered, _EDIT_MARKERS):
        return [
            _classify("edit_strategy"),
            scripted_call("edit_strategy", {"reason": "mock edit: swap the organism"}),
            scripted_call(
                "verify_strategy", {"reason": "mock verification of an edit"}
            ),
            _lead_final(_EDIT_PROSE, "await_user"),
        ]
    if has_any(lowered, _REMEMBER_MARKERS):
        return [
            _classify("memory_request"),
            scripted_call(
                "remember",
                {
                    "kind": "preference",
                    "name": "default organism",
                    "summary": "The user works with Plasmodium falciparum 3D7.",
                    "content": {"organism": "Plasmodium falciparum 3D7"},
                },
            ),
            _lead_final(_REMEMBER_PROSE, "await_user"),
        ]
    if has_any(lowered, LOOP_MARKERS):
        return [
            _classify("new_strategy"),
            scripted_call("frame_problem", {"reason": "mock loop"}),
            _lead_final(_LOOP_PROSE, "await_user"),
        ]
    if has_any(lowered, _VARIANT_MARKERS):
        return [
            _classify("follow_up_question"),
            scripted_call("compare_search_variants", _variant_args()),
            _lead_final(_VARIANT_PROSE, "await_user"),
        ]
    if has_any(lowered, _CONSULT_MARKERS):
        return [
            _classify("new_strategy"),
            scripted_call("consult_user", _consult_args()),
        ]
    return None


def _routed_sequence(messages: list[ModelMessage], raw: str) -> list[ToolCallPart]:
    lowered = raw.lower()
    dispatched = _one_tool_sequence(lowered)
    if dispatched is not None:
        return dispatched
    prose = _prose_only_sequence(lowered)
    if prose is not None:
        return prose
    if has_any(lowered, _ASSENT_MARKERS):
        return _build_branch(messages, raw, classification="extend_strategy")
    build = (
        _FIX_MARKERS
        + _FEEDBACK_MARKERS
        + _GO_MARKERS
        + _BUILD_MARKERS
        + _COMBINED_MARKERS
    )
    if has_any(lowered, build):
        return _build_branch(messages, raw)
    return [_lead_final(f"[mock] {raw}", "await_user")]


def _build_branch(
    messages: list[ModelMessage],
    raw: str,
    *,
    classification: str = "new_strategy",
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
    if not _classified_this_turn(messages):
        return sequence[0]
    return next_unmade_call(sequence[1:], messages)
