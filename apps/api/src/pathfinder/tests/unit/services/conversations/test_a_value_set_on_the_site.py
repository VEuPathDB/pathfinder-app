"""A value moved on VEuPathDB reaches the stored graph before anything else.

The canvas commit and the count refresh both read the strategy on the site
under the write lock, so an edit is planned against the site's value and a
count is stored beside the value it counts.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import NumberValue, StringValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.operations import UpdateStepMetaOp, UpdateStepParamsOp
from pathfinder.tests.unit.services.conversations._site_edit_doubles import (
    CEILING,
    EXPORT,
    JOIN,
    ORGANISM,
    SCORE,
    TAXON,
    WDK,
    canvas,
    install_the_site,
    join_params,
    refresh,
    the_site,
)


class TestAValueSetOnTheSite:
    async def test_the_refresh_stores_the_sites_value_beside_its_count(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = install_the_site(monkeypatch, the_site())

        await refresh(repo)

        assert (repo.value(EXPORT, SCORE), repo.stored.step_counts) == (
            NumberValue(value=12),
            {EXPORT: 85, TAXON: 5000, JOIN: 2},
        )

    async def test_an_edit_of_another_step_writes_that_step_alone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = install_the_site(monkeypatch, the_site())

        await canvas(
            repo,
            UpdateStepParamsOp(
                step_id=TAXON, parameters={ORGANISM: StringValue(value="PvP01")}
            ),
        )

        writes = [c for c in repo.site.calls if c.name.startswith("update_step")]
        assert [(c.name, c.kwargs["step_id"]) for c in writes] == [
            ("update_step_search_config", WDK[TAXON])
        ]
        assert repo.value(EXPORT, SCORE) == NumberValue(value=12)

    async def test_a_rename_leaves_the_sites_value_on_the_site(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = install_the_site(monkeypatch, the_site())

        await canvas(repo, UpdateStepMetaOp(step_id=EXPORT, display_name="export"))

        writes = [c for c in repo.site.calls if c.name.startswith("update_step")]
        assert [(c.name, c.kwargs["step_id"]) for c in writes] == [
            ("update_step_properties", WDK[EXPORT])
        ]
        assert repo.value(EXPORT, SCORE) == NumberValue(value=12)

    async def test_an_edit_of_the_same_step_sends_the_sites_value_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A value the canvas did not name is the one the site holds."""
        repo = install_the_site(monkeypatch, the_site())

        await canvas(
            repo,
            UpdateStepParamsOp(
                step_id=EXPORT, parameters={CEILING: NumberValue(value=25)}
            ),
        )

        (put,) = repo.site.named("update_step_search_config")
        assert put.kwargs["parameters"] == {SCORE: "12", CEILING: "25"}

    async def test_a_value_the_site_holds_in_the_stored_form_is_left_alone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = install_the_site(monkeypatch, the_site(score="10"))
        before = repo.stored.root.model_copy(deep=True)

        await refresh(repo)

        assert repo.stored.root == before

    async def test_an_operator_flipped_on_the_site_is_stored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        site = the_site(score="10")
        site["steps"][str(WDK[JOIN])]["searchConfig"]["parameters"] = join_params(
            "UNION"
        )
        repo = install_the_site(monkeypatch, site)

        await refresh(repo)

        assert repo.stored.root.operator is CombineOp.UNION
