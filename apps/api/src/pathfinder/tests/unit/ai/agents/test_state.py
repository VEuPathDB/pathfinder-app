"""``AgentToolState``: the discovery registry and the params a criterion bound."""

from __future__ import annotations

from veupathdb.domain.parameters.values import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
)
from veupathdb.domain.strategy.operational_spec import Criterion

from pathfinder.ai.agents.state import AgentToolState, SearchOverview


def _ov(
    name: str,
    *,
    parameter_names: list[str] | None = None,
) -> SearchOverview:
    return SearchOverview(
        search_name=name,
        display_name=name,
        record_type="transcript",
        description="",
        parameter_names=parameter_names or ["taxon"],
        required_params=["taxon"],
    )


def test_discovered_search_names_empty_initially() -> None:
    s = AgentToolState()
    assert s.discovered_search_names() == set()


def test_discovered_search_names_returns_all_inspected() -> None:
    s = AgentToolState()
    s.register_search("GenesByGoTerm", _ov("GenesByGoTerm"))
    s.register_search("GenesByText", _ov("GenesByText"))
    assert s.discovered_search_names() == {"GenesByGoTerm", "GenesByText"}


def test_a_search_overview_carries_no_selection_verdict() -> None:
    """No field records a verdict on a search: nothing writes one."""
    absent = {
        "selection_status",
        "rationale",
        "selection_reason",
        "confidence",
        "param_hints",
        "decided",
    }
    assert absent.isdisjoint(SearchOverview.model_fields)
    assert not hasattr(AgentToolState, "decided_search_names")
    assert not hasattr(AgentToolState, "selected_search_names")


def test_param_read_key_is_stable_and_context_sensitive() -> None:
    k1 = AgentToolState.param_read_key("S", "p")
    k2 = AgentToolState.param_read_key("S", "p")
    assert k1 == k2
    ctx_a: dict[str, ParamValue] = {"parent": SinglePickValue(value="a")}
    ctx_b: dict[str, ParamValue] = {"parent": SinglePickValue(value="b")}
    assert AgentToolState.param_read_key("S", "p", context_values=ctx_a) != k1
    assert AgentToolState.param_read_key(
        "S", "p", context_values=ctx_a
    ) != AgentToolState.param_read_key("S", "p", context_values=ctx_b)
    assert AgentToolState.param_read_key("S", "p", query="x") != k1


def test_mark_and_was_param_read() -> None:
    s = AgentToolState()
    key = AgentToolState.param_read_key("S", "p")
    assert s.was_param_read(key) is False
    s.mark_param_read(key)
    assert s.was_param_read(key) is True


def _derisi_criterion() -> Criterion:
    return Criterion(
        id="timecourse",
        text="trophozoite stage expression",
        search_name="GenesByMicroarrayDerisi",
        resolved_params={
            "profileset_generic": SinglePickValue(value="DeRisi 3D7 Smoothed"),
            "channel": SinglePickValue(value="Channel 1"),
        },
    )


class TestResolvedParamsFor:
    def test_returns_the_bound_parents_of_that_search(self) -> None:
        state = AgentToolState()
        state.frame_set_criterion(_derisi_criterion())

        assert state.resolved_params_for("GenesByMicroarrayDerisi") == {
            "profileset_generic": SinglePickValue(value="DeRisi 3D7 Smoothed"),
            "channel": SinglePickValue(value="Channel 1"),
        }

    def test_is_empty_for_a_search_no_criterion_uses(self) -> None:
        state = AgentToolState()
        state.frame_set_criterion(_derisi_criterion())

        assert state.resolved_params_for("GenesByInterproDomain") == {}

    def test_is_empty_when_nothing_is_bound(self) -> None:
        assert AgentToolState().resolved_params_for("GenesByMicroarrayDerisi") == {}

    def test_does_not_leak_across_searches(self) -> None:
        state = AgentToolState()
        state.frame_set_criterion(_derisi_criterion())
        state.frame_set_criterion(
            Criterion(
                id="domain",
                text="kinase domain",
                search_name="GenesByInterproDomain",
                resolved_params={
                    "domain_database": SinglePickValue(value="PFAM"),
                },
            )
        )

        derisi = state.resolved_params_for("GenesByMicroarrayDerisi")

        assert "domain_database" not in derisi

    def test_merges_criteria_that_share_a_search(self) -> None:
        # Two criteria can legitimately bind the same search (e.g. an up- and a
        # down-regulated arm). Their parents together are the context.
        state = AgentToolState()
        state.frame_set_criterion(
            Criterion(
                id="up",
                text="induced",
                search_name="GenesByMicroarrayDerisi",
                resolved_params={
                    "profileset_generic": SinglePickValue(value="DeRisi 3D7 Smoothed")
                },
            )
        )
        state.frame_set_criterion(
            Criterion(
                id="down",
                text="repressed",
                search_name="GenesByMicroarrayDerisi",
                resolved_params={"channel": SinglePickValue(value="Channel 2")},
            )
        )

        merged = state.resolved_params_for("GenesByMicroarrayDerisi")

        assert set(merged) == {"profileset_generic", "channel"}

    def test_ignores_criteria_with_no_search_bound(self) -> None:
        state = AgentToolState()
        state.frame_set_criterion(
            Criterion(id="vague", text="something", search_name="")
        )

        assert state.resolved_params_for("") == {}

    def test_carries_multi_pick_values_unchanged(self) -> None:
        state = AgentToolState()
        state.frame_set_criterion(
            Criterion(
                id="c",
                text="t",
                search_name="S",
                resolved_params={
                    "samples": MultiPickValue(values=["20 Hour", "21 Hour"])
                },
            )
        )

        assert state.resolved_params_for("S") == {
            "samples": MultiPickValue(values=["20 Hour", "21 Hour"])
        }


def test_frame_set_criterion_replaces_by_id() -> None:
    st = AgentToolState()
    st.frame_set_criterion(Criterion(id="c1", text="a", search_name="S1"))
    st.frame_set_criterion(Criterion(id="c1", text="a2", search_name="S2"))
    assert len(st.operational_spec_draft.criteria) == 1
    assert st.operational_spec_draft.criteria[0].search_name == "S2"
