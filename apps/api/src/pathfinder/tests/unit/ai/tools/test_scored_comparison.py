"""``compare_variants_scored`` and its unscored counterpart: the card they
emit, the refusals they raise, and the Lead surface that reaches them."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic_ai.exceptions import ModelRetry
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.tools.standalone import scored_comparison
from pathfinder.ai.tools.standalone._variant_targets import reject_combine_variants
from pathfinder.ai.tools.standalone.scored_comparison import compare_variants_scored
from pathfinder.ai.tools.standalone.variant_comparison import compare_search_variants
from pathfinder.services.control_sets import ControlSetResponse
from pathfinder.services.experiment.scored_comparison import (
    ScoredComparison,
    ScoredVariant,
)
from pathfinder.services.experiment.variant_comparison import VariantSpec
from pathfinder.tests._support.tool_returns import returned, summary_text
from pathfinder.tests.unit.ai.tools.conftest import detached_lead_context

_WDK_STRATEGY_ID = "330531493"


def _variants(first: str = "SA", second: str = "SB") -> list[VariantSpec]:
    return [
        VariantSpec(label="a", search_name=first, parameters={}),
        VariantSpec(label="b", search_name=second, parameters={}),
    ]


def _pin_control_set(
    monkeypatch: pytest.MonkeyPatch,
    *,
    positive_ids: list[str],
    negative_ids: list[str],
) -> None:
    control_set = ControlSetResponse(
        id=str(uuid4()),
        name="controls",
        site_id="plasmodb",
        record_type="transcript",
        positive_ids=positive_ids,
        negative_ids=negative_ids,
        tags=[],
        version=1,
        is_public=False,
        created_at="2026-01-01T00:00:00Z",
    )

    async def _get(
        _session: AsyncSession, _control_set_id: UUID, _user_id: UUID
    ) -> ControlSetResponse:
        return control_set

    monkeypatch.setattr(scored_comparison, "get_control_set", _get)


def _pin_comparison(
    monkeypatch: pytest.MonkeyPatch, comparison: ScoredComparison
) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    async def _run(
        site_id: str, user_id: str | None, variants: Any, **kwargs: Any
    ) -> ScoredComparison:
        del site_id, user_id, variants
        captured.update(kwargs)
        return comparison

    monkeypatch.setattr(scored_comparison, "run_scored_comparison", _run)
    return captured


async def test_it_emits_the_scored_card_and_the_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pin_control_set(monkeypatch, positive_ids=["g1", "g2"], negative_ids=["n1"])
    captured = _pin_comparison(
        monkeypatch,
        ScoredComparison(
            variants=[
                ScoredVariant(
                    label="a", search_name="SA", mcc=0.6, f1=0.8, precision=0.8
                ),
                ScoredVariant(
                    label="b", search_name="SB", mcc=0.9, f1=0.9, precision=0.9
                ),
            ],
            winner_label="b",
            objective="mcc",
        ),
    )

    result = await compare_variants_scored(
        detached_lead_context(),
        _variants(),
        control_set_id=str(uuid4()),
        objective="mcc",
    )

    assert returned(result, ScoredComparison).winner_label == "b"
    assert captured["positive_controls"] == ["g1", "g2"]
    assert captured["objective"] == "mcc"
    assert result.metadata[0].type == "data-scored-comparison"
    assert "Winner: b" in summary_text(result)


async def test_it_refuses_a_single_variant(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_control_set(monkeypatch, positive_ids=["g1"], negative_ids=[])

    with pytest.raises(ModelRetry, match="at least 2"):
        await compare_variants_scored(
            detached_lead_context(),
            [VariantSpec(label="a", search_name="SA", parameters={})],
            control_set_id=str(uuid4()),
        )


class TestTheLeadCanReachControlScoring:
    """A tool dropped from the toolset makes the capability unreachable while
    every unit test of the tool itself keeps passing."""

    def _lead_tool_names(self) -> list[str]:
        return sorted(build_lead_agent()._function_toolset.tools)

    def test_the_scored_comparison_tool_is_registered(self) -> None:
        assert "compare_variants_scored" in self._lead_tool_names()

    def test_the_control_set_tools_it_depends_on_are_registered(self) -> None:
        names = self._lead_tool_names()
        assert "build_control_set" in names
        assert "list_control_sets" in names

    def test_the_unscored_comparison_points_at_the_scored_one(self) -> None:
        assert compare_search_variants.__doc__ is not None
        assert "compare_variants_scored" in compare_search_variants.__doc__

    def test_the_tool_tells_the_model_how_to_report_a_failure(self) -> None:
        assert compare_variants_scored.__doc__ is not None
        assert "scoring failed" in compare_variants_scored.__doc__


class TestAFailedScoringIsReportedAsOne:
    """The Lead must not narrate a failed scoring as a missing control set,
    and the membership question stays answerable."""

    _COMPARISON = ScoredComparison(
        variants=[
            ScoredVariant(
                label="top 20%",
                search_name="SA",
                error="parameters.channel: Input should be a valid string",
                control_hits=["g1"],
            ),
            ScoredVariant(
                label="top 5%",
                search_name="SB",
                error="parameters.channel: Input should be a valid string",
                control_hits=[],
            ),
        ],
        winner_label=None,
        objective="mcc",
    )

    async def _content(self, monkeypatch: pytest.MonkeyPatch) -> str:
        _pin_control_set(monkeypatch, positive_ids=["g1", "g2"], negative_ids=[])
        _pin_comparison(monkeypatch, self._COMPARISON)
        result = await compare_variants_scored(
            detached_lead_context(), _variants(), control_set_id=str(uuid4())
        )
        return summary_text(result)

    async def test_the_summary_says_the_scoring_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        content = await self._content(monkeypatch)

        assert "scoring failed" in content
        assert "Winner" not in content

    async def test_the_summary_carries_membership_per_variant(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        content = await self._content(monkeypatch)

        assert "top 20% contains g1" in content
        assert "top 5% contains none of them" in content


class TestAControlSetIdIsARetry:
    async def test_a_non_uuid_control_set_is_a_retry(self) -> None:
        with pytest.raises(ModelRetry) as err:
            await compare_variants_scored(
                detached_lead_context(), _variants(), _WDK_STRATEGY_ID
            )

        assert "control" in str(err.value).lower()

    async def test_a_name_instead_of_an_id_is_a_retry(self) -> None:
        with pytest.raises(ModelRetry):
            await compare_variants_scored(
                detached_lead_context(), _variants(), "my controls"
            )


class TestACombineStepIsNotAVariant:
    """The live strategy renders a combine step as "Combine", so that word
    reaches the variant tools as a search name. WDK refuses it server-side,
    which spends the run and reports no metric."""

    @pytest.mark.parametrize(
        "combine_name", ["Combine", "__combine__"], ids=["display-label", "sentinel"]
    )
    async def test_the_scored_tool_names_the_offending_search(
        self, combine_name: str
    ) -> None:
        with pytest.raises(ModelRetry) as err:
            await compare_variants_scored(
                detached_lead_context(), _variants(combine_name), str(uuid4())
            )

        assert combine_name in str(err.value)

    async def test_the_message_names_the_tool_that_takes_a_step(self) -> None:
        with pytest.raises(ModelRetry) as err:
            await compare_variants_scored(
                detached_lead_context(), _variants("Combine"), str(uuid4())
            )

        assert "run_control_tests_on_step" in str(err.value)

    async def test_the_offending_label_is_named(self) -> None:
        with pytest.raises(ModelRetry) as err:
            await compare_variants_scored(
                detached_lead_context(), _variants("Combine"), str(uuid4())
            )

        assert "a" in str(err.value)

    async def test_the_unscored_tool_refuses_it_too(self) -> None:
        with pytest.raises(ModelRetry) as err:
            await compare_search_variants(detached_lead_context(), _variants("Combine"))

        assert "run_control_tests_on_step" in str(err.value)

    @pytest.mark.parametrize(
        "search_name",
        ["GenesByMolecularWeight", "GenesByCombinedScore"],
        ids=["plain-search", "name-contains-the-word"],
    )
    def test_a_real_search_still_passes(self, search_name: str) -> None:
        specs = _variants(search_name)

        reject_combine_variants(specs)

        assert [spec.search_name for spec in specs] == [search_name, "SB"]
