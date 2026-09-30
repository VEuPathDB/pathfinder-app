"""A pick the site labels obsolete binds when the site counts records for it,
with its label; one that counts nothing is refused with only what the site
showed, and a term the researcher named is never swapped without a card."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import MultiPickValue, ParamValue
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ParameterInfo, ResolvedParams, format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone import _frame_count
from pathfinder.ai.tools.standalone._frame_measure import labelled_picks
from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    ValueSource,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec import frame_ctx
from pathfinder.tests.unit.services.strategies.test_an_obsolete_term_is_named_at_bind import (
    _GO_TYPEAHEAD,
)

_INFOS = format_param_info_typed([_GO_TYPEAHEAD])
_OBSOLETE = "GO:0009296"
_LABEL = "GO:0009296 : obsolete flagellum assembly : 0"


async def _fetch(_context: dict[str, str]) -> list[ParameterInfo]:
    return _INFOS


def _picked(term: str) -> tuple[CriterionCall, dict[str, BoundValue]]:
    call = CriterionCall(
        criterion_id="c_flagellum",
        search_name="GenesByGoTerm",
        text="flagellum assembly genes",
        params={"go_typeahead": [term]},
    )
    bound = {
        "go_typeahead": BoundValue(value=MultiPickValue(values=[term]), source="chosen")
    }
    return call, bound


@pytest.mark.asyncio
async def test_a_proposed_obsolete_term_is_labelled_not_refused() -> None:
    call, bound = _picked(_OBSOLETE)

    labels = await labelled_picks(_fetch, _INFOS, call, bound)

    assert labels == [
        Measurement(
            kind="vocabulary_label",
            param="go_typeahead",
            reading=_OBSOLETE,
            label=_LABEL,
        )
    ]


def _serve_count(monkeypatch: pytest.MonkeyPatch, count: int | None) -> None:
    async def _count(
        site_id: str,
        record_type: str,
        search_name: str,
        params: Mapping[str, ParamValue],
    ) -> int | None:
        return count

    monkeypatch.setattr(_frame_count, "count_bound_criterion", _count)


async def _record(source: ValueSource, state: AgentToolState) -> int | None:
    value = MultiPickValue(values=[_OBSOLETE])
    criterion = Criterion(
        id="c_flagellum",
        text="flagellum assembly genes",
        search_name="GenesByGoTerm",
        resolved_params={"go_typeahead": BoundValue(value=value, source=source)},
        measurements=[
            Measurement(
                kind="vocabulary_label",
                param="go_typeahead",
                reading=_OBSOLETE,
                label=_LABEL,
            )
        ],
    )
    count, _ = await _frame_count.record_and_count_criterion(
        frame_ctx(state),
        criterion,
        record_type="transcript",
        definition=WDKSearch(url_segment="GenesByGoTerm"),
        resolved=ResolvedParams(params={"go_typeahead": value}),
        infos=_INFOS,
    )
    return count


@pytest.mark.asyncio
async def test_an_obsolete_term_the_site_counts_binds_with_its_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve_count(monkeypatch, 82)
    state = AgentToolState()

    count = await _record("stated", state)

    assert count == 82
    [held] = state.operational_spec_draft.criteria
    assert (held.result_count, held.measurements[0].label) == (82, _LABEL)


@pytest.mark.asyncio
async def test_an_obsolete_term_whose_count_did_not_arrive_binds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve_count(monkeypatch, None)
    state = AgentToolState()

    assert await _record("stated", state) is None
    assert [c.id for c in state.operational_spec_draft.criteria] == ["c_flagellum"]


@pytest.mark.asyncio
async def test_a_stated_obsolete_term_that_counts_nothing_asks_the_researcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve_count(monkeypatch, 0)
    state = AgentToolState()

    with pytest.raises(ModelRetry) as refused:
        await _record("stated", state)

    assert str(refused.value) == (
        f"go_typeahead (GO Term or GO ID) on GenesByGoTerm holds {_OBSOLETE!r}, which "
        f"the site labels {_LABEL!r}: the ontology marks the term obsolete, and the "
        "site counts 0 genes for it at these values. It is not bound. The "
        "researcher named this term, so ask them with a card which entry to use; "
        "the current entries nearest its words are ['GO:0060271 : cilium assembly "
        ": 7', 'GO:0044458 : motile cilium assembly : 8', 'GO:0120316 : sperm "
        "flagellum assembly : 4', 'GO:0042255 : ribosome assembly : 8']."
    )
    assert state.operational_spec_draft.criteria == []


@pytest.mark.asyncio
async def test_a_chosen_obsolete_term_that_counts_nothing_names_the_current_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve_count(monkeypatch, 0)
    state = AgentToolState()

    with pytest.raises(ModelRetry) as refused:
        await _record("chosen", state)

    assert "few or no records" not in str(refused.value)
    assert "Pass a current entry" in str(refused.value)
    assert state.operational_spec_draft.criteria == []
