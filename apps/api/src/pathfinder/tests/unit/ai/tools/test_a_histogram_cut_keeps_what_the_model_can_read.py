"""A histogram longer than the cut keeps its largest categories, or its first ranges."""

from __future__ import annotations

from veupathdb.eda import EdaDistributionResponse

from pathfinder.ai.tools.standalone._eda_bins import cut_histogram


def _distribution(bins: list[tuple[str, float]]) -> EdaDistributionResponse:
    return EdaDistributionResponse.model_validate(
        {
            "histogram": [
                {"value": value, "binStart": label, "binEnd": label, "binLabel": label}
                for label, value in bins
            ],
            "statistics": {"subsetSize": 0, "numVarValues": 0},
        }
    )


def _hosts() -> list[tuple[str, float]]:
    return [(f"host {i:03d}", float(i)) for i in range(100)]


def test_a_categorical_cut_keeps_the_largest_bins_and_states_their_share() -> None:
    cut = cut_histogram(_distribution(_hosts()), data_shape="categorical")

    assert cut.labels == [f"host {i:03d}" for i in range(99, 59, -1)]
    assert cut.values == [float(i) for i in range(99, 59, -1)]
    assert cut.total == 100
    assert cut.note == (
        "100 bins in all; the 40 largest are shown here, holding 3,180 of 4,950 "
        "counted values (64.2%). Bins hold between 0 and 99 each. The figure "
        "shows every bin."
    )


def test_a_flat_cut_says_every_bin_holds_the_same_count() -> None:
    genes = [(f"TGME49_{200000 + i}", 12.0) for i in range(8776)]

    cut = cut_histogram(_distribution(genes), data_shape="categorical")

    assert cut.labels == [f"TGME49_{200000 + i}" for i in range(40)]
    assert cut.note == (
        "8,776 bins in all; the 40 largest are shown here, holding 480 of "
        "105,312 counted values (0.5%). Every bin holds 12. The figure shows "
        "every bin."
    )


def test_a_continuous_cut_keeps_the_first_ranges_in_order() -> None:
    cut = cut_histogram(_distribution(_hosts()), data_shape="continuous")

    assert cut.labels == [f"host {i:03d}" for i in range(40)]
    assert cut.note == (
        "100 bins in all; the first 40 in order are shown here, holding 780 of "
        "4,950 counted values (15.8%). Bins hold between 0 and 99 each. The "
        "figure shows every bin."
    )


def test_a_short_histogram_is_whole_and_carries_no_note() -> None:
    bins = [("P. berghei", 4011.0), ("P. falciparum", 4130.0), ("P. yoelii", 268.0)]

    cut = cut_histogram(_distribution(bins), data_shape="categorical")

    assert (cut.labels, cut.values, cut.total, cut.note) == (
        ["P. berghei", "P. falciparum", "P. yoelii"],
        [4011.0, 4130.0, 268.0],
        3,
        None,
    )


def test_no_distribution_is_an_empty_cut() -> None:
    cut = cut_histogram(None, data_shape=None)

    assert (cut.labels, cut.values, cut.total, cut.note) == ([], [], 0, None)
