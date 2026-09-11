"""The discovery gate the split catalog tools write: the registered overview,
the vocabulary snapshot and the per-turn read ledger."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from pydantic_ai import RunContext
from veupathdb.domain.parameters.values import SinglePickValue
from veupathdb.domain.parameters.wdk_vocab import VocabOption
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.wdk_models import WDKSearchResponse
from veupathdb.wdk.wdk_parameters import WDKParameter
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ParameterNotOnSearch,
    SearchOverviewResult,
    format_search_overview,
    search_inspection,
    searches,
)

from pathfinder.ai.agents.state import (
    AgentToolState,
    ParamVocabSnapshot,
    SearchOverview,
)
from pathfinder.ai.agents.strategy_instructions import pinned_discovered_searches
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone import catalog_discovery
from pathfinder.ai.tools.standalone.catalog_discovery import AlreadyReadNotice
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import (
    agent_run_context,
    patch_search_details,
    wdk_param,
)

_GOAL = "kinase genes expressed in the schizont stage"


def _params(names: list[str]) -> list[WDKParameter]:
    return [wdk_param(name) for name in names]


@dataclass
class _RecordedClient:
    """Serves one recorded WDK search response and records each read."""

    response: WDKSearchResponse
    reads: list[str] = field(default_factory=list)
    contexts: list[dict[str, str]] = field(default_factory=list)

    async def get_search_details(
        self, _record_type: str, search_name: str, *, expand_params: bool = True
    ) -> WDKSearchResponse:
        del expand_params
        self.reads.append(search_name)
        return self.response

    async def get_search_details_with_params(
        self,
        _record_type: str,
        search_name: str,
        context: dict[str, str],
        *,
        expand_params: bool = True,
    ) -> WDKSearchResponse:
        del expand_params
        self.reads.append(search_name)
        self.contexts.append(context)
        return self.response


def _fixture_ctx(
    state: AgentToolState, monkeypatch: pytest.MonkeyPatch, fixture: str
) -> tuple[RunContext[AgentDeps], _RecordedClient]:
    """A context reading one recorded WDK search response."""
    client = _RecordedClient(
        WDKSearchResponse.model_validate(load_recorded(fixture).json_body())
    )
    monkeypatch.setattr(searches, "get_wdk_client", lambda _site: client)
    monkeypatch.setattr(search_inspection, "get_wdk_client", lambda _site: client)
    return agent_run_context(agent_state=state), client


class TestTheSearchOverviewGate:
    """The read writes the gate the service half does not hold."""

    async def test_the_first_read_registers_the_search(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state = AgentToolState()
        state.operational_spec_draft.goal = _GOAL
        ctx, _client = _fixture_ctx(
            state, monkeypatch, "search_genes_by_molecular_weight"
        )

        await catalog_discovery.get_search_overview(
            ctx, search_name="GenesByMolecularWeight", record_type="transcript"
        )

        registered = state.get_overview("GenesByMolecularWeight")
        assert registered is not None
        assert registered.display_name == "Molecular Weight"
        assert registered.record_type == "transcript"
        assert registered.parameter_names == [
            "organism",
            "min_molecular_weight",
            "max_molecular_weight",
        ]
        assert registered.required_params == [
            "organism",
            "min_molecular_weight",
            "max_molecular_weight",
        ]

    async def test_the_draft_goal_ranks_the_sheet(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state = AgentToolState()
        state.operational_spec_draft.goal = _GOAL
        ctx, _client = _fixture_ctx(
            state, monkeypatch, "search_genes_by_molecular_weight"
        )
        captured: dict[str, str | None] = {}
        original = format_search_overview

        def _capture(**kwargs: Any) -> SearchOverviewResult:
            captured["query"] = kwargs["query"]
            return original(**kwargs)

        monkeypatch.setattr(search_inspection, "format_search_overview", _capture)

        await catalog_discovery.get_search_overview(
            ctx, search_name="GenesByMolecularWeight", record_type="transcript"
        )

        assert captured["query"] == _GOAL

    async def test_a_repeat_read_costs_no_wdk_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx, client = _fixture_ctx(
            AgentToolState(), monkeypatch, "search_genes_by_molecular_weight"
        )

        await catalog_discovery.get_search_overview(
            ctx, search_name="GenesByMolecularWeight", record_type="transcript"
        )
        repeat = returned(
            await catalog_discovery.get_search_overview(
                ctx, search_name="GenesByMolecularWeight", record_type="transcript"
            ),
            AlreadyReadNotice,
        )

        assert repeat.kind == "already_read"
        assert client.reads == ["GenesByMolecularWeight"]


class TestTheParameterReadGate:
    async def test_the_read_is_ledgered_and_the_vocabulary_snapshotted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state = AgentToolState()
        ctx, _client = _fixture_ctx(state, monkeypatch, "search_genes_by_location")
        await catalog_discovery.get_search_overview(
            ctx, search_name="GenesByLocation", record_type="transcript"
        )

        first = returned(
            await catalog_discovery.get_parameter_options(
                ctx,
                search_name="GenesByLocation",
                parameter_id="organismSinglePick",
                record_type="transcript",
            ),
            ParameterInfo,
        )
        repeat = returned(
            await catalog_discovery.get_parameter_options(
                ctx,
                search_name="GenesByLocation",
                parameter_id="organismSinglePick",
                record_type="transcript",
            ),
            AlreadyReadNotice,
        )

        assert first.kind == "parameter_info"
        assert repeat.kind == "already_read"
        assert state.read_param_options == {"GenesByLocation|organismSinglePick||"}
        overview = state.get_overview("GenesByLocation")
        assert overview is not None
        assert "organismSinglePick" in overview.param_vocab

    async def test_bound_params_narrow_the_vocabulary_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state = AgentToolState()
        ctx, client = _fixture_ctx(state, monkeypatch, "search_genes_by_location")
        captured: dict[str, Any] = {}

        def _bound(search_name: str) -> dict[str, Any]:
            captured["asked"] = search_name
            return {"organismSinglePick": SinglePickValue(value="P. falciparum 3D7")}

        monkeypatch.setattr(state, "resolved_params_for", _bound)

        result = returned(
            await catalog_discovery.get_parameter_options(
                ctx,
                search_name="GenesByLocation",
                parameter_id="chromosomeOptional",
                record_type="transcript",
            ),
            ParameterInfo,
        )

        assert result.kind == "parameter_info"
        assert captured["asked"] == "GenesByLocation"
        assert client.contexts[0]["organismSinglePick"] == "P. falciparum 3D7"

    async def test_an_unknown_parameter_is_not_ledgered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state = AgentToolState()
        ctx, _client = _fixture_ctx(state, monkeypatch, "search_genes_by_location")

        result = returned(
            await catalog_discovery.get_parameter_options(
                ctx,
                search_name="GenesByLocation",
                parameter_id="organism_single_pick",
                record_type="transcript",
            ),
            ParameterNotOnSearch,
        )

        assert result.kind == "parameter_not_on_search"
        assert state.read_param_options == set()


def _registered_search(name: str, parameter_names: list[str]) -> SearchOverview:
    return SearchOverview(
        search_name=name,
        display_name=name,
        record_type="transcript",
        description="",
        parameter_names=parameter_names,
        required_params=parameter_names[:1],
    )


class TestTheParamVocabSnapshot:
    """A read writes the vocabulary into the state, so planning copies values."""

    async def test_a_read_writes_the_parameter_info_fields(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state = AgentToolState()
        state.register_search(
            "RNASeqHardFloor", _registered_search("RNASeqHardFloor", ["hard_floor"])
        )
        patch_search_details(monkeypatch, parameters=_params(["hard_floor"]))
        info = ParameterInfo(
            name="hard_floor",
            display_name="Hard Floor",
            type="number-enum",
            required=True,
            is_visible=True,
            help="Tier-quantile floor",
            value_format='{"type": "single-pick-vocabulary", "value": "<one>"}',
            default_value="6772.93",
            allowed_values=[
                VocabOption(value="1693.23", display="1693 reads"),
                VocabOption(value="3386.46", display="3386 reads"),
                VocabOption(value="6772.93", display="6772 reads"),
            ],
        )
        monkeypatch.setattr(
            search_inspection, "format_typed_param", lambda *_a, **_kw: info
        )

        result = returned(
            await catalog_discovery.get_parameter_options(
                agent_run_context(agent_state=state),
                search_name="RNASeqHardFloor",
                parameter_id="hard_floor",
            ),
            ParameterInfo,
        )
        assert result is info

        overview = state.get_overview("RNASeqHardFloor")
        assert overview is not None
        snap = overview.param_vocab["hard_floor"]
        assert snap.param_type == "number-enum"
        assert snap.required is True
        assert snap.help == "Tier-quantile floor"
        assert snap.default_value == "6772.93"
        assert snap.allowed_values is not None
        assert [v.value for v in snap.allowed_values] == [
            "1693.23",
            "3386.46",
            "6772.93",
        ]

    async def test_a_second_read_keeps_the_first_snapshot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state = AgentToolState()
        state.register_search(
            "FoldChange",
            _registered_search("FoldChange", ["hard_floor", "fold_change"]),
        )
        patch_search_details(
            monkeypatch, parameters=_params(["hard_floor", "fold_change"])
        )
        info_for = {
            "hard_floor": ParameterInfo(
                name="hard_floor",
                display_name="Hard Floor",
                type="number-enum",
                required=True,
                is_visible=True,
                help="",
                value_format='{"type": "single-pick-vocabulary", "value": "<one>"}',
                default_value="6772.93",
                allowed_values=[VocabOption(value="6772.93", display="6772 reads")],
            ),
            "fold_change": ParameterInfo(
                name="fold_change",
                display_name="Fold change",
                type="number",
                required=False,
                is_visible=True,
                help="",
                value_format='{"type": "number", "value": <number>}',
                default_value="2",
            ),
        }
        monkeypatch.setattr(
            search_inspection,
            "format_typed_param",
            lambda filtered_param, **_kw: info_for[filtered_param.name],
        )

        ctx = agent_run_context(agent_state=state)
        await catalog_discovery.get_parameter_options(
            ctx, search_name="FoldChange", parameter_id="hard_floor"
        )
        await catalog_discovery.get_parameter_options(
            ctx, search_name="FoldChange", parameter_id="fold_change"
        )

        overview = state.get_overview("FoldChange")
        assert overview is not None
        assert set(overview.param_vocab) == {"hard_floor", "fold_change"}

    def test_the_pinned_instruction_renders_the_snapshot(self) -> None:
        state = AgentToolState()
        overview = _registered_search(
            "GenesByRNASeqFoldChange", ["hard_floor"]
        ).model_copy(
            update={
                "display_name": "RNA-Seq Fold Change",
                "param_vocab": {
                    "hard_floor": ParamVocabSnapshot(
                        param_type="number-enum",
                        required=True,
                        help="Tier-quantile floor for read counts",
                        default_value="6772.93",
                        allowed_values=[
                            VocabOption(value="1693.23", display="1693 reads"),
                            VocabOption(value="6772.93", display="6772 reads"),
                        ],
                    ),
                },
            },
        )
        state.register_search(overview.search_name, overview)

        rendered = pinned_discovered_searches(agent_run_context(agent_state=state))

        assert rendered is not None
        assert "param_vocab" in rendered
        assert "hard_floor" in rendered
        assert "1693.23" in rendered
        assert "6772.93" in rendered
        assert "Tier-quantile floor for read counts" in rendered
