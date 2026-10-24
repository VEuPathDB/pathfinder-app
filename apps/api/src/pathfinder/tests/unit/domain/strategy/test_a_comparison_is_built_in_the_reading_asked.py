"""A comparison FRAME classed by its reading is answered by a bound compare term
of that reading, whenever a set it compares holds more than one genome."""

from __future__ import annotations

from veupathdb_mcp.catalog import PhyleticPattern

from pathfinder.domain.strategy.compare_readings import reading_departures
from pathfinder.tests._support.synthetic_taxonomy import pattern, synthetic_tree


def _compare(left: list[str], right: list[str], reading: str) -> PhyleticPattern:
    return pattern(
        {
            "kind": "compare",
            "left": {"kind": "codes", "codes": left},
            "right": {"kind": "codes", "codes": right},
            "reading": reading,
            "condition": "more_than",
        }
    )


_ONE_GENOME = pattern(
    {
        "kind": "count",
        "of": {"kind": "codes", "codes": ["fna"]},
        "measure": "proteins",
        "condition": "at_least",
        "value": 3,
    }
)


def test_an_average_built_as_averages_stands() -> None:
    bound = [("c_more", _compare(["FERN"], ["MOSS"], "averages"))]

    assert reading_departures("averages", bound, synthetic_tree()) == []


def test_an_average_built_per_genome_is_sent_back() -> None:
    bound = [("c_more", _compare(["FERN"], ["MOSS"], "per_genome"))]

    assert reading_departures("averages", bound, synthetic_tree()) == [
        (
            "c_more compares FERN (3 genomes) with MOSS (2 genomes) by per_genome, "
            "and the request asks for averages: averages answers a question about "
            "proteins per genome, an average or a ratio, each set's proteins "
            "divided by its genome count. Build the compare again with reading "
            "averages and bind its handle."
        )
    ]


def test_an_average_built_as_one_genomes_count_is_sent_back() -> None:
    bound = [("c_more", _ONE_GENOME)]

    assert reading_departures("averages", bound, synthetic_tree()) == [
        (
            "The request compares two sets of genomes, and c_more binds no compare "
            "term. Build it with build_phyletic_expression as a compare with "
            "reading averages and bind its handle: a count over one genome does "
            "not answer a comparison of two sets."
        )
    ]


def test_two_single_genomes_read_alike_in_every_reading() -> None:
    bound = [("c_more", _compare(["fna"], ["msa"], "totals"))]

    assert reading_departures("averages", bound, synthetic_tree()) == []


def test_a_total_built_as_averages_is_sent_back() -> None:
    bound = [("c_more", _compare(["FERN"], ["lna"], "averages"))]

    [sentence] = reading_departures("totals", bound, synthetic_tree())

    assert sentence.startswith(
        "c_more compares FERN (3 genomes) with lna (1 genome) by averages, and the "
        "request asks for totals: totals answers a question about the sets pooled"
    )


def test_nothing_bound_is_nothing_to_hold() -> None:
    assert reading_departures("per_genome", [], synthetic_tree()) == []
