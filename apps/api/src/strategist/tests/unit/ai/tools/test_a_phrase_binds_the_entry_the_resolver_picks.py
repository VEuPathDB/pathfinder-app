from __future__ import annotations

from collections.abc import Mapping

import pytest
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import (
    ParameterInfo,
    VocabNarrowing,
    VocabPick,
    format_param_info_typed,
)

from strategist.ai.tools.standalone._vocab_resolution import bound_proposal
from strategist.tests._support.recorded_searches import suite_search

_TEXT = suite_search("search_genes_by_text")
_FIELDS = next(
    info
    for info in format_param_info_typed(list(_TEXT.parameters or []))
    if info.name == "text_fields"
)


def _pick(value: str | None, confidence: float) -> VocabPick:
    return VocabPick(
        value=value,
        display=value,
        choice_confidence=confidence,
        fit_probability=confidence,
        min_confidence=0.8,
        offered=4,
    )


class _Resolver:
    def __init__(self, picks: Mapping[str, VocabPick | None]) -> None:
        self.picks = picks
        self.asked: list[tuple[str, str, str]] = []

    async def read(
        self,
        site_id: str,
        search_name: str,
        parameter_id: str,
        *,
        record_type: str | None = None,
        context_values: Mapping[str, object] | None = None,
        narrowing: VocabNarrowing | None = None,
    ) -> ParameterInfo:
        del site_id, record_type, context_values
        assert narrowing is not None
        phrase = narrowing.terms[0]
        self.asked.append((search_name, parameter_id, phrase))
        return _FIELDS.model_copy(update={"vocab_pick": self.picks.get(phrase)})


@pytest.fixture
def resolver(monkeypatch: pytest.MonkeyPatch) -> _Resolver:
    def install(picks: Mapping[str, VocabPick | None]) -> _Resolver:
        built = _Resolver(picks)
        monkeypatch.setattr(catalog, "read_parameter_options", built.read)
        return built

    return install({})


async def test_an_exact_entry_is_bound_without_asking_the_resolver(
    resolver: _Resolver,
) -> None:
    bound = await bound_proposal("plasmodb", "GenesByText", _FIELDS, ["product"])

    assert (bound, resolver.asked) == (["product"], [])


async def test_a_phrase_binds_the_entry_a_settled_pick_names(
    resolver: _Resolver,
) -> None:
    resolver.picks = {"gene product": _pick("product", 0.94)}

    bound = await bound_proposal("plasmodb", "GenesByText", _FIELDS, ["gene product"])

    assert (bound, resolver.asked) == (
        ["product"],
        [("GenesByText", "text_fields", "gene product")],
    )


async def test_a_phrase_an_unsettled_pick_answers_stays_as_proposed(
    resolver: _Resolver,
) -> None:
    resolver.picks = {"anything": _pick("product", 0.5), "nothing": _pick(None, 0.9)}

    bound = await bound_proposal(
        "plasmodb", "GenesByText", _FIELDS, ["anything", "nothing", "unread"]
    )

    assert bound == ["anything", "nothing", "unread"]


async def test_a_list_binds_each_phrase_in_order(
    resolver: _Resolver,
) -> None:
    resolver.picks = {"gene product": _pick("product", 0.94)}

    bound = await bound_proposal(
        "plasmodb", "GenesByText", _FIELDS, ["gene product", "product"]
    )

    assert bound == ["product", "product"]
