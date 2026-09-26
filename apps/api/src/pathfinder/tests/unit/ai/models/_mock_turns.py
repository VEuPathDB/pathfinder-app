"""Plays one role of the mock through a whole arc, answering each call as its
tool would, with the instructions the real renderers pin."""

from __future__ import annotations

import contextvars
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from assistant_core.conversation.history import HISTORY_PROCESSORS
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from veupathdb.domain.parameters import (
    VocabOption,
)
from veupathdb_mcp.catalog import SheetEntry

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.agents.strategy_instructions import (
    pinned_frame_sheets,
    pinned_frame_workspace,
    pinned_graph_state,
)
from pathfinder.ai.lead.lead_pins import pinned_eda_sheet
from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.lead.verify_dispatch import RootSample, work_order
from pathfinder.ai.models.mock import role_script
from pathfinder.ai.models.mock.arc import Role
from pathfinder.ai.models.mock.faults import made_by_a_fault
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.domain.eda_parts import EdaFilterSheetEntry
from pathfinder.domain.separation import AttachedControls
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.step_rationale import SearchRationale
from pathfinder.domain.strategy.step_words import AddedSearch
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests.unit.ai.models._mock_pins import framed_pins
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

# Each site's organism sheet: the site organism, one of its genus, one beyond.
SHEET_ORGANISMS = {
    "plasmodb": [
        "Plasmodium falciparum 3D7",
        "Plasmodium vivax P01",
        "Toxoplasma gondii ME49",
    ],
    "vectorbase": [
        "Anopheles gambiae PEST",
        "Anopheles stephensi Indian",
        "Aedes aegypti LVP_AGWG",
    ],
    "toxodb": [
        "Toxoplasma gondii ME49",
        "Toxoplasma gondii GT1",
        "Neospora caninum Liverpool",
    ],
    "veupathdb": [
        "Neospora caninum Liverpool",
        "Neospora caninum Liverpool 2019",
        "Toxoplasma gondii ME49",
    ],
}
SHEET_PARAMS = {
    "GenesWithSignalPeptide": ["organism", "signalp_version"],
    "GenesByTransmembraneDomains": ["organism", "min_tm", "max_tm"],
    "GenesByOrthologs": ["organism", "isSyntenic"],
    "GenesByText": [
        "text_search_organism",
        "text_expression",
        "text_fields",
        "document_type",
    ],
    "GenesByGoTerm": ["organism", "go_typeahead", "go_term_evidence", "go_term_slim"],
    "GenesByGeneType": ["organism", "geneType", "includePseudogenes"],
    "GenesByExportPrediction": ["organism", "min_exportpred_score"],
    "GenesByMolecularWeight": [
        "organism",
        "min_molecular_weight",
        "max_molecular_weight",
    ],
}
BUILT_ROOT_WDK_ID = 102
# The step a build or an edit reports it added, as the tool answers it.
ADDED_SEARCH = AddedSearch(
    step_id="step_sp",
    search_display_name="Predicted Signal Peptide",
    criterion_text="genes with a predicted signal peptide",
    rationale=SearchRationale(
        search_name="GenesWithSignalPeptide",
        basis="parameter",
        term="SignalP version",
        reason="sets SignalP version to the value the request states",
        tool_call_id="call_bind",
    ),
)
SAVED_GENE_COUNT = 116
OWN_EXPERIMENT_SEARCH = "GenesByOwnExperiment"
LIVE_ROOT_COUNT = 1203
STRATEGY_ROOT_WDK_ID = 555
LIVE_ROOT_WDK_ID = 900_003
GENE_SET_ID = "gs-7"
CONTROL_SET_ID = "cs-1"
NOT_HERE = "This study is on another site; its genes are not genes of this site."
# The refusal each named tool sends back, by tool name.
Refusals = Mapping[str, str]


def _entry(name: str, vocabulary: list[str]) -> SheetEntry:
    return SheetEntry(
        name=name,
        display_name=name,
        type="multi-pick-vocabulary",
        required=True,
        vocabulary=[VocabOption(value=v, display=v) for v in vocabulary],
    )


# The GO terms a GO search's sheet lists first.
SHEET_GO_TERMS = ["GO:0016301", "GO:0004672"]


def _sheet(site_id: str, search_name: str) -> list[SheetEntry]:
    vocabularies = {
        "organism": SHEET_ORGANISMS[site_id],
        "go_typeahead": SHEET_GO_TERMS,
    }
    names = SHEET_PARAMS.get(search_name, ["organism"])
    return [_entry(name, vocabularies.get(name, [])) for name in names]


class _Tools:
    """The answers of one run, and the sheets its FRAME holds open."""

    def __init__(self, site_id: str, graph: StrategyGraph | None) -> None:
        self.site_id = site_id
        self.state = AgentToolState()
        self.lead_ctx = lead_run_context()
        self.values = SiteValues.for_site(site_id)
        self.session = StrategySession(site_id)
        if graph is not None:
            self.session.add_graph(graph)

    def instructions(self, base: str) -> str:
        ctx = agent_run_context(agent_state=self.state, strategy_session=self.session)
        pins = (
            pinned_frame_sheets(ctx),
            pinned_frame_workspace(ctx),
            pinned_graph_state(ctx),
        )
        frame = "\n\n".join(block for block in pins if block)
        eda = pinned_eda_sheet(self.lead_ctx) or ""
        return "\n\n".join(part for part in (base, frame, eda) if part)

    def _criterion(self, args: dict[str, Any]) -> dict[str, Any]:
        cid = str(args["criterion_id"])
        search = str(args["search_name"])
        if "params" not in args:
            self.state.pin_sheet(
                cid, search, _sheet(self.site_id, search), what_runs=search
            )
            names = SHEET_PARAMS.get(search, ["organism"])
            return {
                "criterionId": cid,
                "searchName": search,
                "paramsTemplate": dict.fromkeys(names),
            }
        self.state.frame_set_criterion(
            Criterion(id=cid, text=str(args["text"]), search_name=search)
        )
        return {
            "criterionId": cid,
            "searchName": search,
            "resolvedParams": args["params"],
        }

    def _eda_filters(self, args: dict[str, Any]) -> dict[str, Any]:
        if "filters" in args:
            self.lead_ctx.deps.state.domain.close_eda_sheet()
            return {"applied": True}
        self.lead_ctx.deps.state.domain.pin_eda_sheet(
            str(args["dataset_id"]),
            [
                EdaFilterSheetEntry(
                    entity_id="sample",
                    variable_id="genotype",
                    display_name="Genotype",
                    filter_type="stringSet",
                    vocabulary=["wildtype", "delta mutant"],
                    vocabulary_total=2,
                )
            ],
        )
        return {"sheetPinned": True}

    def answer(self, call: ToolCallPart) -> object:
        args = call.args_as_dict()
        organism = self.values.organism
        positives = self.values.controls.positive_ids
        added = ADDED_SEARCH.model_dump(by_alias=True, mode="json")
        fixed: dict[str, object] = {
            "frame_problem": {
                "summary": "The pass bound what it could.",
                "disposition": "spec_ready",
            },
            "build_strategy": {
                "outcome": {
                    "rootCount": 12,
                    "nodeResults": [
                        {"wdkStepId": 101},
                        {"wdkStepId": BUILT_ROOT_WDK_ID},
                    ],
                },
                "addedSearches": [added],
            },
            "verify_strategy": {"digest": {"success": True}},
            "edit_strategy": {"diff": {}, "addedSearches": [added]},
            "get_strategy": {
                "steps": [
                    {
                        "id": "step_root",
                        "wdkStepId": STRATEGY_ROOT_WDK_ID,
                        "parameters": {
                            "organism": {
                                "type": "multi-pick-vocabulary",
                                "values": [organism],
                            }
                        },
                    }
                ]
            },
            "get_sample_records": {
                "records": [{"id": f"{g}.1"} for g in positives[:2]]
            },
            "read_gene_record": {
                "geneId": args.get("gene_id", ""),
                "organism": organism,
                "product": "a conserved protein",
                "recordUrl": f"https://{self.site_id}.example/record",
            },
            "get_live_strategy_state": {"rootCount": LIVE_ROOT_COUNT},
            "rename_strategy": (
                f"Renamed the strategy to {args.get('name', '')}. "
                f"It returns {LIVE_ROOT_COUNT:,} genes."
            ),
            "clear_strategy": {"graphId": "g1", "message": "cleared"},
            "propose_changes": {"diff": {}},
            "build_control_set": {"controlSetId": CONTROL_SET_ID},
            "save_gene_set": {
                "geneSetCreated": {"id": "gs-1", "geneCount": SAVED_GENE_COUNT}
            },
            "list_gene_sets": {"geneSets": [{"id": GENE_SET_ID}]},
            "export_gene_set": {"downloadUrl": "https://files.example/set.csv"},
            "search_for_searches": [
                {"name": OWN_EXPERIMENT_SEARCH, "displayName": "Own experiment"},
                {"otherSites": {"experiments": [{"datasetId": "DS_elsewhere"}]}},
            ],
            "read_experiment": {"name": "A blood meal series", "site": "another site"},
            "note": {"id": "note-1"},
            "separate_controls": {"result": {"taskId": "task-1"}},
            "adopt_separating_strategy": {
                "addedSearches": [
                    {"searchDisplayName": "Signal", "rationale": {"term": "40 genes"}}
                ]
            },
            "search_eda_studies": {
                "studies": [
                    {"datasetId": "DS_here"},
                    {"datasetId": "DS_there", "notHere": NOT_HERE},
                ]
            },
            "open_eda_analysis": {"analysisId": "a1"},
        }
        if call.tool_name == "set_criterion":
            return self._criterion(args)
        if call.tool_name == "set_eda_filters":
            return self._eda_filters(args)
        if call.tool_name == "describe_eda_study":
            return _described("entity_id" in args)
        return fixed.get(call.tool_name, "ok")


def _described(entity: bool) -> dict[str, object]:
    return {
        "entities": [
            {"entityId": "sample"},
            {"entityId": "counts", "parentEntityId": "sample"},
        ],
        "geneEntityId": "counts",
        "variables": [{"variableId": "SEQUENCE_READ_COUNT_SENSE"}] if entity else [],
    }


@dataclass(frozen=True)
class Scene:
    """What surrounds a run: the instructions pinned on it, the refusals its
    tools send back, and the refusals they send back to a fault's calls only."""

    instructions: str = ""
    refused: Refusals = field(default_factory=dict)
    faulted: Refusals = field(default_factory=dict)
    answers: Mapping[str, object] = field(default_factory=dict)
    """Answers that replace the fixed ones, by tool name."""
    later_instructions: str | None = None
    """The instructions pinned after the first request, when they change."""
    graph: StrategyGraph | None = None
    """The strategy graph the run's instructions pin, as a sub-agent reads it."""

    def refusal(self, call: ToolCallPart) -> str | None:
        if call.tool_name in self.refused:
            return self.refused[call.tool_name]
        if made_by_a_fault(call) and call.tool_name in self.faulted:
            return self.faulted[call.tool_name]
        return None


def seen_by_the_model(messages: list[ModelMessage]) -> list[ModelMessage]:
    """The history every agent's processors hand the model."""
    for processor in HISTORY_PROCESSORS:
        messages = processor(messages)
    return messages


def play(
    role: Role,
    site_id: str,
    text: str,
    *,
    work_order: str | None = None,
    scene: Scene | None = None,
    limit: int = 40,
) -> list[ToolCallPart]:
    """Every call ``role`` makes in one run, until it answers or hits ``limit``."""
    setting = scene or Scene()
    instructions = setting.instructions
    script = role_script(role)
    tools = _Tools(site_id, setting.graph)

    def run() -> list[ToolCallPart]:
        bind_scripted_scope(site_id, text)
        prompt = UserPromptPart(content=text if work_order is None else work_order)
        messages: list[ModelMessage] = [
            ModelRequest(parts=[prompt], instructions=tools.instructions(instructions)),
        ]
        calls: list[ToolCallPart] = []
        for _ in range(limit):
            call = script(seen_by_the_model(messages))
            calls.append(call)
            refusal = setting.refusal(call)
            if call.tool_name == "final_result" and refusal is None:
                break
            messages.append(ModelResponse(parts=[call]))
            reply: RetryPromptPart | ToolReturnPart = (
                RetryPromptPart(
                    content=refusal,
                    tool_name=call.tool_name,
                    tool_call_id=call.tool_call_id,
                )
                if refusal is not None
                else ToolReturnPart(
                    tool_name=call.tool_name,
                    content=setting.answers[call.tool_name]
                    if call.tool_name in setting.answers
                    else tools.answer(call),
                    tool_call_id=call.tool_call_id,
                )
            )
            later = setting.later_instructions
            pinned = instructions if later is None else later
            messages.append(
                ModelRequest(parts=[reply], instructions=tools.instructions(pinned))
            )
        return calls

    return contextvars.copy_context().run(run)


def names(calls: list[ToolCallPart]) -> list[str]:
    return [call.tool_name for call in calls]


def args_of(calls: list[ToolCallPart], tool: str) -> list[dict[str, Any]]:
    return [call.args_as_dict() for call in calls if call.tool_name == tool]


def as_json(calls: list[ToolCallPart]) -> str:
    return json.dumps([call.args_as_dict() for call in calls])


def built_thread() -> Scene:
    """A framed thread whose live read names a root the site holds."""
    return Scene(
        instructions=framed_pins(),
        answers={
            "get_live_strategy_state": {
                "rootCount": LIVE_ROOT_COUNT,
                "steps": [
                    {"stepId": "step_leaf", "wdkStepId": 900_001, "isRoot": False},
                    {
                        "stepId": "step_root",
                        "wdkStepId": LIVE_ROOT_WDK_ID,
                        "isRoot": True,
                    },
                ],
            }
        },
    )


def verify_order(count: int, controls: AttachedControls | None = None) -> str:
    """VERIFY's work order over a root of ``count`` records."""
    root = RootSample(
        step_id="step_root", wdk_step_id=STRATEGY_ROOT_WDK_ID, count=count
    )
    return work_order("mock verification", controls, root)
