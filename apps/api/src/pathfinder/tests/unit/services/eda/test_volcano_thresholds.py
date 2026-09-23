"""Thresholding is the consumer's job: the viz endpoint sends every row."""

from __future__ import annotations

import json

import pytest
from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaDifferentialExpressionConfig,
    VolcanoStatsResponse,
)
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

from pathfinder.domain.eda_parts import EdaComparison
from pathfinder.services.eda.compute import (
    NoComputationError,
    VolcanoThresholds,
    analysis_comparison,
    comparison_of,
    retained_point_ids,
    retained_summary,
    volcano_view,
)

FIXTURES = FIXTURE_DIR

_CUT = VolcanoThresholds(effect_size_threshold=1.0, significance_threshold=0.05)


def _stats(rows: list[dict[str, str]]) -> VolcanoStatsResponse:
    return VolcanoStatsResponse.model_validate(
        {"effectSizeLabel": "log2(Fold Change)", "statistics": rows}
    )


def test_a_row_at_the_effect_size_threshold_is_retained() -> None:
    """The bridge plugin's test is inclusive on the absolute effect size."""
    summary = retained_summary(
        _stats([{"effectSize": "1.0", "pValue": "0.01", "pointID": "A"}]),
        effect_size_threshold=1.0,
        significance_threshold=0.05,
    )
    assert summary.retained == 1
    assert summary.retained_up == 1
    assert summary.retained_down == 0


def test_a_row_at_the_significance_threshold_is_retained() -> None:
    summary = retained_summary(
        _stats([{"effectSize": "2.0", "pValue": "0.05", "pointID": "A"}]),
        effect_size_threshold=1.0,
        significance_threshold=0.05,
    )
    assert summary.retained == 1


def test_a_row_below_the_effect_size_threshold_is_dropped() -> None:
    summary = retained_summary(
        _stats([{"effectSize": "0.99", "pValue": "0.001", "pointID": "A"}]),
        effect_size_threshold=1.0,
        significance_threshold=0.05,
    )
    assert summary.retained == 0


def test_a_row_above_the_p_value_threshold_is_dropped() -> None:
    summary = retained_summary(
        _stats([{"effectSize": "5.0", "pValue": "0.06", "pointID": "A"}]),
        effect_size_threshold=1.0,
        significance_threshold=0.05,
    )
    assert summary.retained == 0


def test_a_negative_effect_size_counts_as_down() -> None:
    summary = retained_summary(
        _stats([{"effectSize": "-3.0", "pValue": "0.01", "pointID": "A"}]),
        effect_size_threshold=1.0,
        significance_threshold=0.05,
    )
    assert summary.retained == 1
    assert summary.retained_down == 1


def test_up_only_keeps_the_positive_side() -> None:
    rows = [
        {"effectSize": "3.0", "pValue": "0.01", "pointID": "UP"},
        {"effectSize": "-3.0", "pValue": "0.01", "pointID": "DOWN"},
    ]
    ids = retained_point_ids(
        _stats(rows),
        effect_size_threshold=1.0,
        significance_threshold=0.05,
        effect_direction="upOnly",
    )
    assert ids == ["UP"]


def test_down_only_keeps_the_negative_side() -> None:
    rows = [
        {"effectSize": "3.0", "pValue": "0.01", "pointID": "UP"},
        {"effectSize": "-3.0", "pValue": "0.01", "pointID": "DOWN"},
    ]
    ids = retained_point_ids(
        _stats(rows),
        effect_size_threshold=1.0,
        significance_threshold=0.05,
        effect_direction="downOnly",
    )
    assert ids == ["DOWN"]


def test_the_default_direction_keeps_both_sides() -> None:
    """A missing effectDirection is the review card's upAndDown, never upOnly."""
    rows = [
        {"effectSize": "3.0", "pValue": "0.01", "pointID": "UP"},
        {"effectSize": "-3.0", "pValue": "0.01", "pointID": "DOWN"},
    ]
    ids = retained_point_ids(
        _stats(rows), effect_size_threshold=1.0, significance_threshold=0.05
    )
    assert ids == ["UP", "DOWN"]


def test_a_row_with_no_p_value_is_counted_as_unparseable_and_never_retained() -> None:
    """One of 5511 live rows omits pValue; such a row cannot pass a cut."""
    summary = retained_summary(
        _stats(
            [
                {"effectSize": "-1.49447459261845", "pointID": "PF3D7_MIT04200"},
                {"effectSize": "3.0", "pValue": "0.01", "pointID": "A"},
            ]
        ),
        effect_size_threshold=1.0,
        significance_threshold=0.05,
    )
    assert summary.total_rows == 2
    assert summary.unparseable_rows == 1
    assert summary.retained == 1


def test_a_non_numeric_string_is_counted_as_unparseable() -> None:
    summary = retained_summary(
        _stats([{"effectSize": "NA", "pValue": "NA", "pointID": "A"}]),
        effect_size_threshold=1.0,
        significance_threshold=0.05,
    )
    assert summary.unparseable_rows == 1
    assert summary.retained == 0


def test_an_unparseable_row_never_reaches_the_point_ids() -> None:
    ids = retained_point_ids(
        _stats(
            [
                {"effectSize": "-1.49447459261845", "pointID": "PF3D7_MIT04200"},
                {"effectSize": "3.0", "pValue": "0.01", "pointID": "A"},
            ]
        ),
        effect_size_threshold=1.0,
        significance_threshold=0.05,
    )
    assert ids == ["A"]


def test_a_row_with_no_p_value_is_plotted_at_its_effect_size_and_never_kept() -> None:
    """The x coordinate is readable, so the reader must see the gene is there."""
    view = volcano_view(
        _stats(
            [
                {"effectSize": "-1.49447459261845", "pointID": "PF3D7_MIT04200"},
                {"effectSize": "3.0", "pValue": "0.01", "pointID": "A"},
            ]
        ),
        thresholds=_CUT,
    )
    assert [point.point_id for point in view.points] == ["PF3D7_MIT04200", "A"]
    silent = view.points[0]
    assert silent.effect_size == -1.49447459261845
    assert silent.p_value is None
    assert silent.adjusted_p_value is None
    assert silent.retained is False
    assert view.total_points == 2
    assert view.retained_points == 1


def test_a_row_with_an_unreadable_p_value_is_plotted_as_one_with_none() -> None:
    view = volcano_view(
        _stats([{"effectSize": "2.0", "pValue": "NA", "pointID": "A"}]),
        thresholds=_CUT,
    )
    assert len(view.points) == 1
    assert view.points[0].p_value is None
    assert view.points[0].retained is False


def test_a_row_with_no_readable_effect_size_has_no_x_and_is_dropped() -> None:
    view = volcano_view(
        _stats(
            [
                {"effectSize": "NA", "pValue": "0.01", "pointID": "NOX"},
                {"effectSize": "3.0", "pValue": "0.01", "pointID": "A"},
            ]
        ),
        thresholds=_CUT,
    )
    assert [point.point_id for point in view.points] == ["A"]
    assert view.total_points == 2


def test_the_recorded_statistics_plot_every_row_that_has_an_effect_size() -> None:
    """The one recorded row without a p-value is drawn, not silently missing."""
    raw = json.loads((FIXTURES / "volcano_statistics.json").read_text())
    view = volcano_view(VolcanoStatsResponse.model_validate(raw), thresholds=_CUT)
    assert view.total_points == 201
    assert len(view.points) == 201
    assert view.retained_points == 67
    silent = [point for point in view.points if point.p_value is None]
    assert [point.point_id for point in silent] == ["PF3D7_MIT04200"]
    assert silent[0].retained is False


def test_the_recorded_statistics_reproduce_the_measured_gene_counts() -> None:
    """The trimmed fixture pins internal consistency; the live lane pins 1543."""
    raw = json.loads((FIXTURES / "volcano_statistics.json").read_text())
    stats = VolcanoStatsResponse.model_validate(raw)
    summary = retained_summary(
        stats, effect_size_threshold=1.0, significance_threshold=0.05
    )
    assert summary.retained == summary.retained_up + summary.retained_down
    assert summary.total_rows == len(stats.statistics)
    assert summary.retained == len(
        retained_point_ids(
            stats, effect_size_threshold=1.0, significance_threshold=0.05
        )
    )
    assert summary.retained_up + summary.retained_down + summary.unparseable_rows > 0


def test_raising_the_effect_size_threshold_never_grows_the_retained_set() -> None:
    """The cut is monotone in the effect size at a fixed significance."""
    raw = json.loads((FIXTURES / "volcano_statistics.json").read_text())
    stats = VolcanoStatsResponse.model_validate(raw)
    previous: set[str] | None = None
    for effect_size_threshold in (0.5, 1.0, 1.5, 2.0, 3.0, 4.5):
        current = set(
            retained_point_ids(
                stats,
                effect_size_threshold=effect_size_threshold,
                significance_threshold=0.05,
            )
        )
        if previous is not None:
            assert current <= previous
        previous = current
    assert previous is not None


def test_the_two_directions_partition_the_retained_set() -> None:
    """upOnly and downOnly split upAndDown with no row in both halves."""
    raw = json.loads((FIXTURES / "volcano_statistics.json").read_text())
    stats = VolcanoStatsResponse.model_validate(raw)
    both = set(
        retained_point_ids(
            stats, effect_size_threshold=1.0, significance_threshold=0.05
        )
    )
    up = set(
        retained_point_ids(
            stats,
            effect_size_threshold=1.0,
            significance_threshold=0.05,
            effect_direction="upOnly",
        )
    )
    down = set(
        retained_point_ids(
            stats,
            effect_size_threshold=1.0,
            significance_threshold=0.05,
            effect_direction="downOnly",
        )
    )
    assert up | down == both
    assert up & down == set()
    assert len(both) == 67


def _config(group_a: list[str], group_b: list[str]) -> EdaDifferentialExpressionConfig:
    return EdaDifferentialExpressionConfig.model_validate(
        {
            "identifierVariable": {
                "entityId": "ENT_a0b79706",
                "variableId": "VEUPATHDB_GENE_ID",
            },
            "valueVariable": {
                "entityId": "ENT_a0b79706",
                "variableId": "SEQUENCE_READ_COUNT",
            },
            "comparator": {
                "variable": {"entityId": "ENT_8151325d", "variableId": "VAR_64c65374"},
                "groupA": [{"label": label} for label in group_a],
                "groupB": [{"label": label} for label in group_b],
            },
        }
    )


def test_the_comparison_keeps_every_label_of_each_group_in_order() -> None:
    comparison = comparison_of(_config(["24h pbm"], ["18h pbm", "36h pbm"]))
    assert comparison == EdaComparison(
        group_a=["24h pbm"], group_b=["18h pbm", "36h pbm"]
    )


def test_an_analysis_with_no_compute_has_no_comparison() -> None:
    analysis = EdaAnalysisDetail(
        analysis_id="C3WiXt0",
        display_name="Aedes aegypti 24h",
        study_id="DS_a91f666e84",
        num_filters=0,
        num_computations=0,
        descriptor=EdaAnalysisDescriptor(),
    )
    with pytest.raises(NoComputationError):
        analysis_comparison(analysis)
