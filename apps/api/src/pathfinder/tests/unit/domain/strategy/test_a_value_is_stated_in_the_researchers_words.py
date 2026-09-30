"""A value is stated when a researcher message holds it: on the scale the
researcher wrote it, as an ordinal, or by the label the site gives it."""

from __future__ import annotations

from veupathdb.domain.parameters import (
    MultiPickValue,
    NumberValue,
    ParamValue,
    StringValue,
)
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.domain.strategy.value_source import (
    stated_by_labels,
    stated_run,
    value_source,
)
from pathfinder.tests._support.recorded_searches import suite_search

_LOG2 = "log2(Fold Change)"
_LOOSEN = "loosen the fold change to 1.5-fold"
_TIGHTEN = "tighten it to the 95th percentile and tell me how the final count changes?"
# The organism vocabularies amoebadb and piroplasmadb publish for GenesByTaxon.
_AMOEBADB = [
    "Acanthamoeba castellanii str. Neff",
    "Dictyostelium discoideum AX4",
    "Entamoeba histolytica HM-1:IMSS",
    "Entamoeba histolytica HM-1:IMSS-A",
    "Naegleria fowleri ATCC 30863",
    "Naegleria fowleri strain ATCC 30894",
    "Naegleria fowleri strain Ty",
]
_PIROPLASMADB = [
    "Babesia bigemina strain BOND",
    "Babesia microti",
    "Babesia microti strain RI",
    "Theileria orientalis Fish Creek",
    "Theileria orientalis strain Shintoku",
]
# The clade tree labels of vectorbase's phyletic codes.
_VECTORBASE_TREE = ["Anopheles gambiae PEST", "Anopheles funestus FUMOZ"]
# Two TriTrypDB haplotypes one word apart.
_TRITRYPDB = [
    "Trypanosoma cruzi CL Brener Esmeraldo-like",
    "Trypanosoma cruzi CL Brener Non-Esmeraldo-like",
]


def _source(value: ParamValue, texts: list[str], display_name: str = "") -> str:
    return value_source(
        value,
        initial_display_value=None,
        request_texts=texts,
        display_name=display_name,
    )


def test_the_log2_of_a_stated_fold_is_stated_by_the_fold() -> None:
    assert (
        _source(NumberValue(value=0.585), [_LOOSEN], _LOG2),
        stated_run(NumberValue(value=0.585), [_LOOSEN], display_name=_LOG2),
    ) == ("stated", "1.5-fold")


def test_a_folds_number_bound_on_the_log2_scale_is_not_stated() -> None:
    assert _source(NumberValue(value=1.5), [_LOOSEN], _LOG2) == "chosen"


def test_a_number_on_a_parameter_that_names_no_scale_is_stated_as_written() -> None:
    assert _source(NumberValue(value=1.5), [_LOOSEN]) == "stated"


def test_a_stated_fold_states_a_fold_parameter() -> None:
    assert _source(
        StringValue(value="2"), ["at least 2-fold"], "fold difference >="
    ) == ("stated")


def test_an_ordinal_states_its_number() -> None:
    assert (
        _source(NumberValue(value=95), [_TIGHTEN]),
        stated_run(NumberValue(value=95), [_TIGHTEN]),
    ) == ("stated", "95th")


def test_an_organism_is_stated_without_the_word_that_names_its_rank() -> None:
    assert [
        stated_by_labels(
            ["Acanthamoeba castellanii str. Neff"],
            _AMOEBADB,
            ["Acanthamoeba castellanii Neff genes with a signal peptide"],
        ),
        stated_by_labels(
            ["Babesia microti strain RI"],
            _PIROPLASMADB,
            ["Now try Babesia microti RI instead."],
        ),
        stated_by_labels(
            ["Naegleria fowleri strain ATCC 30894"],
            _AMOEBADB,
            ["Naegleria fowleri ATCC 30894"],
        ),
    ] == [
        "Acanthamoeba castellanii Neff",
        "Babesia microti RI",
        "Naegleria fowleri ATCC 30894",
    ]


def test_a_phyletic_code_is_stated_by_its_tree_label() -> None:
    assert stated_by_labels(
        ["Anopheles gambiae PEST"],
        _VECTORBASE_TREE,
        ["which ones have an ortholog in Anopheles gambiae PEST?"],
    ) == ("Anopheles gambiae PEST")


def test_words_that_name_another_entry_as_well_state_neither() -> None:
    assert [
        stated_by_labels(
            ["Trypanosoma cruzi CL Brener Non-Esmeraldo-like"],
            _TRITRYPDB,
            ["Trypanosoma cruzi CL Brener Esmeraldo-like genes"],
        ),
        stated_by_labels(
            ["Entamoeba histolytica HM-1:IMSS-A"],
            _AMOEBADB,
            ["Entamoeba histolytica HM-1:IMSS genes"],
        ),
    ] == ["", ""]


def test_a_label_the_message_does_not_name_is_not_stated() -> None:
    assert stated_by_labels(
        ["Babesia microti strain RI"], _PIROPLASMADB, ["Babesia microti genes"]
    ) == ("")


def test_every_label_of_a_value_is_stated_in_one_message() -> None:
    assert [
        stated_by_labels(
            _VECTORBASE_TREE,
            _VECTORBASE_TREE,
            ["orthologs in Anopheles gambiae PEST and Anopheles funestus FUMOZ"],
        ),
        stated_by_labels(
            _VECTORBASE_TREE,
            _VECTORBASE_TREE,
            ["Anopheles gambiae PEST", "Anopheles funestus FUMOZ"],
        ),
    ] == ["Anopheles gambiae PEST, Anopheles funestus FUMOZ", ""]


def test_a_vocabulary_that_does_not_hold_the_label_admits_only_the_whole_label() -> (
    None
):
    assert [
        stated_by_labels(["Babesia microti strain RI"], [], ["Babesia microti RI"]),
        stated_by_labels(
            ["Babesia microti strain RI"], [], ["Babesia microti strain RI"]
        ),
    ] == ["", "Babesia microti strain RI"]


def test_two_entries_that_differ_by_one_inner_word_are_named_by_neither() -> None:
    vocabulary = ["Babesia microti strain RI", "Babesia microti isolate RI"]

    assert [
        stated_by_labels(["Babesia microti strain RI"], vocabulary, [text])
        for text in ("Babesia microti RI genes", "Babesia microti strain RI genes")
    ] == ["", "Babesia microti strain RI"]


_KNOWLESI = (
    "Plasmodium knowlesi strain H genes with a Plasmodium-specific domain that "
    "have no ortholog in Homo sapiens."
)


def _phyletic_labels() -> list[str]:
    """The clade tree labels plasmodb publishes for the ortholog pattern search."""
    sheet = format_param_info_typed(
        suite_search("search_genes_by_ortholog_pattern").parameters or []
    )
    excluded = next(info for info in sheet if info.name == "excluded_species")
    return [option.display for option in excluded.vocabulary()]


def test_a_label_is_stated_without_its_last_word_that_names_no_other_entry() -> None:
    labels = _phyletic_labels()

    assert (
        "Homo sapiens REF" in labels,
        stated_by_labels(
            ["Homo sapiens REF"],
            labels,
            [_KNOWLESI],
        ),
    ) == (True, "Homo sapiens")


def test_a_label_without_its_last_word_names_nothing_when_another_entry_shares_it() -> (
    None
):
    vocabulary = ["Plasmodium falciparum 3D7", "Plasmodium falciparum IT"]

    assert (
        stated_by_labels(
            ["Plasmodium falciparum 3D7"], vocabulary, ["Plasmodium falciparum genes"]
        )
        == ""
    )


def test_a_label_is_stated_with_its_punctuation_left_out() -> None:
    labels = _phyletic_labels()
    message = "Mus musculus C57BL/6J genes on chromosome 17 near the H2 complex"

    assert (
        "Mus musculus C57BL6J" in labels,
        stated_by_labels(["Mus musculus C57BL6J"], labels, [message]),
        stated_run(MultiPickValue(values=["Mus musculus C57BL6J"]), [message]),
    ) == (True, "Mus musculus C57BL/6J", "Mus musculus C57BL/6J")


_MURIS_MESSAGE = (
    "Giardia muris Roberts-Thompson genes with a cysteine-rich protein annotation."
)


def _giardiadb_organisms() -> list[str]:
    """The organism labels giardiadb publishes for its text search."""
    sheet = format_param_info_typed(
        suite_search("search_giardiadb_genes_by_text").parameters or []
    )
    organism = next(info for info in sheet if info.name == "text_search_organism")
    return [option.display for option in organism.vocabulary()]


def test_a_long_word_one_letter_off_states_the_one_label_it_names() -> None:
    labels = _giardiadb_organisms()

    assert (
        "Giardia muris strain Roberts-Thomson" in labels,
        stated_by_labels(
            ["Giardia muris strain Roberts-Thomson"],
            labels,
            [_MURIS_MESSAGE],
        ),
    ) == (True, "Giardia muris Roberts-Thompson")


def test_a_word_with_a_digit_is_never_one_letter_off() -> None:
    vocabulary = ["Plasmodium falciparum 3D7", "Plasmodium falciparum IT"]

    assert [
        stated_by_labels(
            ["Plasmodium falciparum 3D7"], vocabulary, ["Plasmodium falciparum 3D8"]
        ),
        stated_by_labels(
            ["Isolate PA123456"], ["Isolate PA123456"], ["Isolate PA123457"]
        ),
    ] == ["", ""]


def test_a_short_word_one_letter_off_states_nothing() -> None:
    assert (
        stated_by_labels(
            ["Leishmania major Friedlin"],
            ["Leishmania major Friedlin"],
            ["Leishmania majer Friedlin"],
        )
        == ""
    )


def test_two_labels_one_letter_apart_are_named_by_neither() -> None:
    vocabulary = ["Giardia muris strain Robertsen", "Giardia muris strain Robertson"]

    assert [
        stated_by_labels([label], vocabulary, ["Giardia muris Robertsan genes"])
        for label in vocabulary
    ] == ["", ""]


def test_only_one_word_of_a_label_may_be_one_letter_off() -> None:
    assert (
        stated_by_labels(
            ["Trichomonas vaginalis G3"],
            ["Trichomonas vaginalis G3"],
            ["Trichomona vaginalys G3 genes"],
        )
        == ""
    )
