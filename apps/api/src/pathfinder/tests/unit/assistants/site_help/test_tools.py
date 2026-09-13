"""The pilot's two read-only tools, over the real site registry."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import RunContext
from pydantic_ai.usage import RunUsage
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import RecordTypeInfo

from pathfinder.assistants.site_help import agent
from pathfinder.assistants.site_help.agent import (
    SiteDetail,
    SiteHelpDeps,
    SiteSummary,
    describe_site,
    list_veupathdb_sites,
)
from pathfinder.assistants.site_help.organisms import MAX_SPECIES
from pathfinder.tests._support.tool_returns import returned, wire_size

_TOXO_STRAINS = ("ME49", "GT1", "VEG")

# Three of plasmodb's own organism terms.
_PLASMODB_ORGANISMS = [
    "Plasmodium falciparum 3D7",
    "Plasmodium berghei ANKA",
    "Haemoproteus tartakovskyi strain SISKIN1",
]


def _ctx() -> RunContext[SiteHelpDeps]:
    return RunContext(
        deps=SiteHelpDeps(site_id="plasmodb"),
        model=TestModel(),
        usage=RunUsage(),
        messages=[],
        tool_call_id="call_1",
    )


async def test_it_lists_the_registered_sites_with_their_urls() -> None:
    sites = returned(await list_veupathdb_sites(_ctx()), list[SiteSummary])

    by_id = {site.site_id: site for site in sites}
    assert {"plasmodb", "toxodb", "vectorbase"} <= set(by_id)
    assert by_id["plasmodb"].url.startswith("https://")
    assert by_id["plasmodb"].display_name


async def test_an_unknown_site_is_answered_with_the_ids_that_exist() -> None:
    """The model picked a name; it is told the real ones rather than a 404."""
    with pytest.raises(ModelRetry) as raised:
        await describe_site(_ctx(), "plasmadb")

    assert "plasmodb" in str(raised.value)


async def test_it_counts_the_searches_of_each_record_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The catalog reads are the services'; the join and the counts are ours."""

    async def _record_types(site_id: str) -> list[RecordTypeInfo]:
        assert site_id == "plasmodb"
        return [
            RecordTypeInfo(name="transcript", display_name="Genes"),
            RecordTypeInfo(name="organism", display_name="Organisms"),
        ]

    async def _searches(site_id: str, record_type: str) -> list[WDKSearch]:
        del site_id
        if record_type != "transcript":
            return []
        return [WDKSearch(url_segment=f"search_{index}") for index in range(3)]

    async def _organisms(site_id: str) -> list[str]:
        del site_id
        return ["Plasmodium falciparum 3D7"]

    monkeypatch.setattr(agent, "list_organisms", _organisms)
    monkeypatch.setattr(agent, "get_record_types", _record_types)
    monkeypatch.setattr(agent, "get_raw_searches", _searches)

    detail = returned(await describe_site(_ctx(), "plasmodb"), SiteDetail)

    assert detail.site_id == "plasmodb"
    assert detail.display_name
    assert [(rt.name, rt.search_count) for rt in detail.record_types] == [
        ("transcript", 3),
        ("organism", 0),
    ]


_TOXO_ORGANISMS = [
    "Besnoitia besnoiti UOFL1",
    "Hammondia hammondi H.H.34",
    *(f"Toxoplasma gondii {strain}" for strain in _TOXO_STRAINS),
]


async def test_it_names_the_species_a_site_covers_and_counts_their_strains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The organism question is answered from the site's own vocabulary."""

    async def _organisms(site_id: str) -> list[str]:
        assert site_id == "toxodb"
        return _TOXO_ORGANISMS

    async def _record_types(site_id: str) -> list[RecordTypeInfo]:
        del site_id
        return [RecordTypeInfo(name="transcript", display_name="Genes")]

    async def _searches(site_id: str, record_type: str) -> list[WDKSearch]:
        del site_id, record_type
        return []

    monkeypatch.setattr(agent, "list_organisms", _organisms)
    monkeypatch.setattr(agent, "get_record_types", _record_types)
    monkeypatch.setattr(agent, "get_raw_searches", _searches)

    detail = returned(await describe_site(_ctx(), "toxodb"), SiteDetail)

    gondii = next(o for o in detail.organisms if o.species == "Toxoplasma gondii")
    assert gondii.strain_count == len(_TOXO_STRAINS)
    assert gondii.strains == list(_TOXO_STRAINS)
    assert detail.organism_count == len(_TOXO_ORGANISMS)
    assert detail.species_count == 3
    assert detail.organism_note == ""


# The widest vocabulary of the family, as one tool result must carry it.
_SITE_DETAIL_CEILING = 4_000


def _fungidb_organisms() -> list[str]:
    """267 species of three strains each, the shape the largest site has."""
    return [
        f"Aspergillus species{index:03d} strain{strain}"
        for index in range(267)
        for strain in range(3)
    ]


async def test_a_site_with_hundreds_of_species_answers_within_one_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole vocabulary in one result is a cost the turn cannot carry."""

    async def _organisms(site_id: str) -> list[str]:
        del site_id
        return _fungidb_organisms()

    async def _record_types(site_id: str) -> list[RecordTypeInfo]:
        del site_id
        return [RecordTypeInfo(name="transcript", display_name="Genes")]

    async def _searches(site_id: str, record_type: str) -> list[WDKSearch]:
        del site_id, record_type
        return []

    monkeypatch.setattr(agent, "list_organisms", _organisms)
    monkeypatch.setattr(agent, "get_record_types", _record_types)
    monkeypatch.setattr(agent, "get_raw_searches", _searches)

    answer = await describe_site(_ctx(), "fungidb")

    detail = returned(answer, SiteDetail)
    assert len(detail.organisms) == MAX_SPECIES
    assert detail.species_count == 267
    assert detail.organism_count == 801
    assert "242 more species" in detail.organism_note
    assert wire_size(answer, "describe_site") < _SITE_DETAIL_CEILING


async def test_a_genus_answers_with_that_genus_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _organisms(site_id: str) -> list[str]:
        del site_id
        return ["Toxoplasma gondii ME49", "Hammondia hammondi H.H.34"]

    async def _record_types(site_id: str) -> list[RecordTypeInfo]:
        del site_id
        return []

    monkeypatch.setattr(agent, "list_organisms", _organisms)
    monkeypatch.setattr(agent, "get_record_types", _record_types)

    detail = returned(await describe_site(_ctx(), "toxodb", "Toxoplasma"), SiteDetail)

    assert [o.species for o in detail.organisms] == ["Toxoplasma gondii"]
    assert detail.organism_count == 1


async def test_a_genus_the_site_does_not_carry_names_the_genera_it_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A count of zero from a filter would read as a site with no organisms."""

    async def _organisms(site_id: str) -> list[str]:
        del site_id
        return _PLASMODB_ORGANISMS

    monkeypatch.setattr(agent, "list_organisms", _organisms)

    with pytest.raises(ModelRetry) as raised:
        await describe_site(_ctx(), "plasmodb", "Aspergillus")

    message = str(raised.value)
    assert "Aspergillus" in message
    assert "Haemoproteus" in message
    assert "Plasmodium" in message


async def test_the_answer_names_the_genus_it_was_narrowed_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The counts are the genus's, so the payload says which genus they are."""

    async def _organisms(site_id: str) -> list[str]:
        del site_id
        return _PLASMODB_ORGANISMS

    async def _record_types(site_id: str) -> list[RecordTypeInfo]:
        del site_id
        return []

    monkeypatch.setattr(agent, "list_organisms", _organisms)
    monkeypatch.setattr(agent, "get_record_types", _record_types)

    detail = returned(await describe_site(_ctx(), "plasmodb", "Plasmodium"), SiteDetail)

    assert detail.genus == "Plasmodium"
    assert detail.organism_count == 2
    assert [o.species for o in detail.organisms] == [
        "Plasmodium berghei",
        "Plasmodium falciparum",
    ]


async def test_the_whole_site_names_no_genus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _organisms(site_id: str) -> list[str]:
        del site_id
        return _PLASMODB_ORGANISMS

    async def _record_types(site_id: str) -> list[RecordTypeInfo]:
        del site_id
        return []

    monkeypatch.setattr(agent, "list_organisms", _organisms)
    monkeypatch.setattr(agent, "get_record_types", _record_types)

    detail = returned(await describe_site(_ctx(), "plasmodb"), SiteDetail)

    assert detail.genus == ""
    assert detail.organism_count == 3
