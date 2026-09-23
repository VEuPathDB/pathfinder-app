"""A shape moved on VEuPathDB reaches the stored graph, and what does not.

A step removed, added or replaced on the site leaves or joins the stored
graph. A graph the site does not wholly hold keeps its shape.
"""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import CombineOp, walk

from pathfinder.domain.strategy.operations import UpdateStepMetaOp
from pathfinder.services.strategies import site_changes
from pathfinder.tests.unit.services.conversations._site_edit_doubles import (
    EXPORT,
    JOIN,
    SCORE,
    TAXON,
    WDK,
    canvas,
    install_the_site,
    refresh,
    site_step,
    the_site,
    wired,
)


class TestAShapeChangedOnTheSite:
    async def test_a_step_removed_on_the_site_leaves_the_stored_graph(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        site = the_site(
            tree={"stepId": WDK[EXPORT]},
            drop=frozenset({WDK[TAXON], WDK[JOIN]}),
        )
        repo = install_the_site(monkeypatch, site)

        await refresh(repo)

        assert (wired(repo), repo.stored.wdk_step_ids) == (
            {EXPORT: []},
            {EXPORT: WDK[EXPORT]},
        )

    async def test_a_step_added_on_the_site_joins_the_stored_graph(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        site = the_site(
            tree={
                "stepId": 600,
                "primaryInput": {
                    "stepId": WDK[JOIN],
                    "primaryInput": {"stepId": WDK[EXPORT]},
                    "secondaryInput": {"stepId": WDK[TAXON]},
                },
                "secondaryInput": {"stepId": 555},
            },
            extra={
                "555": site_step(555, "GenesBySignalP", {"min_signalp": "7"}, 900),
                "600": site_step(
                    600,
                    "boolean_question_transcript",
                    {"bq_operator": "MINUS"},
                    1,
                ),
            },
        )
        repo = install_the_site(monkeypatch, site)

        await refresh(repo)

        (added,) = [n for n in walk(repo.stored.root) if n.id == "555"]
        assert wired(repo) == {
            EXPORT: [],
            TAXON: [],
            JOIN: [EXPORT, TAXON],
            "555": [],
            "600": [JOIN, "555"],
        }
        assert (added.search_name, added.parameters) == (
            "GenesBySignalP",
            {"min_signalp": NumberValue(value=7)},
        )
        assert (repo.stored.root.operator, repo.stored.wdk_step_ids) == (
            CombineOp.MINUS,
            {**WDK, "555": 555, "600": 600},
        )

    async def test_a_step_replaced_on_the_site_by_another_search_is_replaced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A WDK step runs the search it was made with, so a new search is a new step."""
        site = the_site(
            tree={
                "stepId": WDK[JOIN],
                "primaryInput": {"stepId": 777},
                "secondaryInput": {"stepId": WDK[TAXON]},
            },
            extra={"777": site_step(777, "GenesBySignalP", {"min_signalp": "5"}, 300)},
            drop=frozenset({WDK[EXPORT]}),
        )
        repo = install_the_site(monkeypatch, site)

        await refresh(repo)

        assert wired(repo) == {"777": [], TAXON: [], JOIN: ["777", TAXON]}
        assert EXPORT not in (repo.stored.wdk_step_ids or {})

    async def test_a_canvas_edit_after_a_site_delete_does_not_put_the_step_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        site = the_site(
            tree={"stepId": WDK[EXPORT]},
            drop=frozenset({WDK[TAXON], WDK[JOIN]}),
        )
        repo = install_the_site(monkeypatch, site)

        await canvas(repo, UpdateStepMetaOp(step_id=EXPORT, display_name="export"))

        assert [c.name for c in repo.site.calls if c.name.startswith("create")] == []
        assert wired(repo) == {EXPORT: []}


class TestWhatTheSiteDoesNotSettle:
    async def test_a_graph_holding_a_step_the_site_lacks_keeps_its_shape(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A draft is not on the site, so no WDK tree says where it stood."""
        repo = install_the_site(
            monkeypatch,
            the_site(
                tree={"stepId": WDK[EXPORT]},
                drop=frozenset({WDK[TAXON], WDK[JOIN]}),
            ),
        )
        stored = repo.thread[1].strategy_ast
        stored["wdkStepIds"] = {EXPORT: WDK[EXPORT], JOIN: WDK[JOIN]}

        await refresh(repo)

        assert wired(repo) == {EXPORT: [], TAXON: [], JOIN: [EXPORT, TAXON]}
        assert repo.value(EXPORT, SCORE) == NumberValue(value=12)

    async def test_a_site_that_does_not_answer_leaves_the_canvas_edit_to_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = install_the_site(monkeypatch, the_site())

        async def _silent(*_args: Any, **_kwargs: Any) -> None:
            return None

        monkeypatch.setattr(site_changes, "read_the_live_strategy", _silent)

        await canvas(repo, UpdateStepMetaOp(step_id=EXPORT, display_name="export"))

        assert [c.name for c in repo.site.calls if c.name.startswith("update")] == [
            "update_step_properties"
        ]
        assert repo.value(EXPORT, SCORE) == NumberValue(value=10)
