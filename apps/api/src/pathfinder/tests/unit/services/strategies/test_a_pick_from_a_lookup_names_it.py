"""A pick from a vocabulary lookup names the lookup and how many of its
matches it took, and each picked entry whose label holds no word of the
looked-up concept is measured. A read that lists no entry counts no pick."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue
from veupathdb_mcp.catalog import PhrasingMatch, VocabLookup, format_param_info_typed

from pathfinder.ai.agents.state import ParamVocabSnapshot
from pathfinder.domain.strategy.measurement_clauses import measurement_clauses
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
)
from pathfinder.services.strategies.cut_picks import OptionsRead, read_picks
from pathfinder.tests._support.recorded_searches import suite_search
from pathfinder.tests.unit.domain.strategy.test_a_taxon_the_message_names_takes_its_organisms import (
    BABESIA_LEAVES,
)

_DOMAINS = "domain_typeahead"
_GO = "go_typeahead"
_PROTEASES = {
    "PF00112": "PF00112 : Papain family cysteine protease",
    "PF00648": "PF00648 : Calpain family cysteine protease",
    "PF02338": "PF02338 : OTU-like cysteine protease",
    "PF15913": "PF15913 : Furin-like repeat, cysteine-rich",
    "PF04140": "PF04140 : Isoprenylcysteine carboxyl methyltransferase (ICMT) family",
}
_PROTEASE_LOOKUP = VocabLookup(
    terms=["cysteine protease", "cysteine proteinase"],
    matches=[
        PhrasingMatch(
            term="cysteine protease",
            phrasing="cysteine protease",
            reach="phrase",
            values=["PF00112", "PF00648", "PF02338"],
        ),
        PhrasingMatch(
            term="cysteine proteinase",
            phrasing="cysteine",
            reach="word",
            values=["PF15913", "PF04140"],
        ),
    ],
)
# The fungidb labels a lookup of "lipase" returned, and the 26 entries bound.
_LIPASES = {
    "GO:0052714": "mannosyl-inositol phosphorylceramide phospholipase activity",
    "GO:0004806": "triacylglycerol lipase activity",
    "GO:0016004": "phospholipase activator activity",
    "GO:0034479": "phosphatidylglycerol phospholipase C activity",
    "GO:0004629": "phospholipase C activity",
    "GO:0034480": "phosphatidylcholine phospholipase C activity",
    "GO:0047499": "calcium-independent phospholipase A2 activity",
    "GO:0007200": (
        "phospholipase C-activating G protein-coupled receptor signaling pathway"
    ),
    "GO:0004465": "lipoprotein lipase activity",
    "GO:0052712": "inositol phosphosphingolipid phospholipase activity",
    "GO:0047372": "monoacylglycerol lipase activity",
    "GO:0004630": "phospholipase D activity",
    "GO:0047498": "calcium-dependent phospholipase A2 activity",
    "GO:0004621": "glycosylphosphatidylinositol phospholipase D activity",
    "GO:0070290": "N-acylphosphatidylethanolamine-specific phospholipase D activity",
    "GO:0052713": "inositol phosphorylceramide phospholipase activity",
    "GO:0004623": "phospholipase A2 activity",
    "GO:0016005": "phospholipase A2 activator activity",
    "GO:0060229": "lipase activator activity",
    "GO:0102545": "phospholipase B activity",
    "GO:0008970": "phospholipase A1 activity",
    "GO:0004620": "phospholipase activity",
    "GO:0120558": "lysophospholipase activity",
    "GO:0016298": "lipase activity",
    "GO:0004622": "phosphatidylcholine lysophospholipase activity",
    "GO:0004435": "phosphatidylinositol-4,5-bisphosphate phospholipase C activity",
}
_PATHWAY = "GO:0007200"


def _criterion(param: str, picks: list[str], labels: dict[str, str]) -> Criterion:
    return Criterion(
        id="c_pick",
        text="the concept",
        search_name="GenesByInterproDomain",
        resolved_params={
            param: BoundValue(value=MultiPickValue(values=picks), source="chosen")
        },
        param_display_names={param: "Specific Domain(s)"},
        measurements=[
            Measurement(
                kind="vocabulary_label", param=param, label=labels[p], reading=p
            )
            for p in picks
            if p in labels
        ],
        result_count=42,
    )


def _proteases(picks: list[str]) -> Criterion:
    return _criterion(_DOMAINS, picks, _PROTEASES)


_WHOLE = OptionsRead(
    param=_DOMAINS, shown=frozenset(_PROTEASES), total=None, lookup=_PROTEASE_LOOKUP
)


def test_a_pick_from_a_whole_lookup_names_the_lookup_and_its_matches() -> None:
    criterion = _proteases(["PF00112", "PF00648", "PF02338"])

    assert read_picks(criterion, [_WHOLE]) == [
        Measurement(
            kind="picked_from_a_lookup",
            param=_DOMAINS,
            count=3,
            unchosen_count=2,
            reading="'cysteine protease', 'cysteine proteinase'",
        )
    ]


def test_the_lookup_clause_says_n_of_the_matches() -> None:
    criterion = _proteases(["PF00112", "PF00648", "PF02338"])
    measured = criterion.model_copy(
        update={"measurements": read_picks(criterion, [_WHOLE])}
    )

    assert measurement_clauses(measured, noun="gene") == [
        (
            "Specific Domain(s) took 3 of the 5 entries that match "
            "'cysteine protease', 'cysteine proteinase'"
        )
    ]


def test_a_pick_the_lookup_did_not_match_takes_none_of_its_matches() -> None:
    labels = {"PF03392": "PF03392 : Insect pheromone-binding family, A10/OS-D"}
    odorant = VocabLookup(terms=["odorant"])
    read = OptionsRead(
        param=_DOMAINS,
        shown=frozenset({"PF02949", "PF14778"}),
        total=None,
        lookup=odorant,
    )

    assert read_picks(_criterion(_DOMAINS, ["PF03392"], labels), [read]) == [
        Measurement(
            kind="picked_from_a_lookup",
            param=_DOMAINS,
            count=0,
            unchosen_count=2,
            reading="'odorant'",
        ),
        Measurement(
            kind="label_without_the_concept",
            param=_DOMAINS,
            label=labels["PF03392"],
            reading="'odorant'",
        ),
    ]


def test_only_the_entry_whose_label_holds_no_word_of_the_concept_is_measured() -> None:
    lookup = VocabLookup(terms=["lipase", "lipase activity"])
    read = OptionsRead(param=_GO, shown=frozenset(_LIPASES), total=None, lookup=lookup)

    gaps = [
        m
        for m in read_picks(_criterion(_GO, list(_LIPASES), _LIPASES), [read])
        if m.kind == "label_without_the_concept"
    ]

    assert gaps == [
        Measurement(
            kind="label_without_the_concept",
            param=_GO,
            label=_LIPASES[_PATHWAY],
            reading="'lipase', 'lipase activity'",
        )
    ]


def test_a_read_with_no_lookup_measures_no_label() -> None:
    shown = frozenset(_PROTEASES)
    whole = OptionsRead(param=_DOMAINS, shown=shown, total=None, lookup=None)

    assert read_picks(_proteases(["PF00112"]), [whole]) == []


def test_a_tree_lookup_lists_no_entry_so_it_counts_no_pick() -> None:
    """The piroplasmadb organism tree read for Babesia, kept as the tree."""
    [organism] = [
        info
        for info in format_param_info_typed(
            suite_search("search_genes_by_taxon_piroplasmadb").parameters or []
        )
        if info.name == "organism"
    ]
    babesia = VocabLookup(
        terms=["Babesia"],
        matches=[
            PhrasingMatch(
                term="Babesia",
                phrasing="babesia",
                reach="phrase",
                values=BABESIA_LEAVES,
            )
        ],
    )
    snapshot = ParamVocabSnapshot.model_validate(
        organism.model_copy(update={"vocab_lookup": babesia}), from_attributes=True
    )
    read = snapshot.options_read("organism")
    criterion = _criterion(
        "organism", BABESIA_LEAVES, {leaf: leaf for leaf in BABESIA_LEAVES}
    )

    assert (
        snapshot.allowed_values,
        read_picks(criterion, [] if read is None else [read]),
    ) == (None, [])
