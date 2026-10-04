"""A statistic the EDA service computed is a fact: a ``stat`` reference renders
its value, a bare number it holds names that reference, and the facts list it."""

from __future__ import annotations

from pathfinder.domain.eda_parts import (
    EdaBoxplotBox,
    EdaPcaAxis,
    EdaPcaPart,
    EdaPcaSeries,
    EdaStatisticRow,
    EdaStatisticsPart,
)
from pathfinder.domain.reply_references import ProseFault, prose_faults, render_reply
from pathfinder.domain.statistic_facts import (
    StatisticFact,
    StatisticRowFact,
    pca_fact,
    statistic_id,
    statistics_fact,
)
from pathfinder.domain.turn_facts import TurnFacts

_PCA_ID = statistic_id("pca", ["ENT_fd574cd6.NORMALIZED_EXPRESSION", "sex"])
_PCA = EdaPcaPart(
    statistic_id=_PCA_ID,
    dataset_id="DS_1a2b3c4d5e",
    analysis_id="t4fszEJ",
    axes=[
        EdaPcaAxis(variable_id="PC1", display_name="PC1 (41.2%)"),
        EdaPcaAxis(variable_id="PC2", display_name="PC2 (17.8%)"),
    ],
    series=[
        EdaPcaSeries(
            label="female",
            x=[-12.5, -11.0],
            y=[1.5, -0.5],
            sample_ids=["S1", "S2"],
        ),
        EdaPcaSeries(
            label="male", x=[10.0, 13.5], y=[0.25, -1.0], sample_ids=["S3", "S4"]
        ),
    ],
)
_TWO_BY_TWO = EdaStatisticsPart(
    statistic_id="stat_9f2c4e1a",
    dataset_id="DS_1a2b3c4d5e",
    analysis_id="t4fszEJ",
    kind="two_by_two",
    title="Two-by-two table of infection status by sex",
    table=None,
    boxes=[],
    trend=None,
    rows=[
        EdaStatisticRow(
            name="odds ratio",
            value="3.25",
            p_value="0.0412",
            confidence_interval="1.05-10.06",
        ),
    ],
)


def test_a_statistic_id_is_the_same_for_the_same_variables() -> None:
    assert statistic_id("trend", ["E.a", "E.b"]) == statistic_id(
        "trend", ["E.a", "E.b"]
    )
    assert statistic_id("trend", ["E.a", "E.b"]) != statistic_id(
        "boxplot", ["E.a", "E.b"]
    )
    assert len(statistic_id("trend", ["E.a"])) == len("stat_") + 8


def test_a_reduction_is_its_axes_where_each_group_sits_and_what_separates() -> None:
    assert pca_fact(_PCA) == StatisticFact(
        id=_PCA_ID,
        kind="pca",
        title="PCA of 4 samples",
        rows=[
            StatisticRowFact(name="PC1", value="41.2%"),
            StatisticRowFact(name="PC2", value="17.8%"),
            StatisticRowFact(name="samples", value="4 samples"),
            StatisticRowFact(name="groups", value="2 groups"),
            StatisticRowFact(name="female PC1 range", value="-12.5 to -11"),
            StatisticRowFact(name="female PC1 mean", value="-11.75"),
            StatisticRowFact(name="female PC2 range", value="-0.5 to 1.5"),
            StatisticRowFact(name="female PC2 mean", value="0.5"),
            StatisticRowFact(name="male PC1 range", value="10 to 13.5"),
            StatisticRowFact(name="male PC1 mean", value="11.75"),
            StatisticRowFact(name="male PC2 range", value="-1 to 0.25"),
            StatisticRowFact(name="male PC2 mean", value="-0.375"),
        ],
        statements=[
            "PC1 separates female from male; their ranges on PC1 do not overlap.",
            "PC2 separates no pair of groups; every pair's ranges on PC2 overlap.",
        ],
    )


def test_a_rows_p_value_and_interval_are_values_of_their_own() -> None:
    assert statistics_fact(_TWO_BY_TWO).rows == [
        StatisticRowFact(name="odds ratio", value="3.25"),
        StatisticRowFact(name="odds ratio p-value", value="0.0412"),
        StatisticRowFact(name="odds ratio confidence interval", value="1.05-10.06"),
    ]


def test_each_box_names_its_five_numbers_its_mean_and_its_outliers() -> None:
    part = _TWO_BY_TWO.model_copy(
        update={
            "kind": "boxplot",
            "rows": [],
            "boxes": [
                EdaBoxplotBox(
                    label="female",
                    lower_fence=1.0,
                    q1=2.0,
                    median=3.5,
                    q3=4.0,
                    upper_fence=6.0,
                    mean=None,
                    outlier_count=1,
                )
            ],
        }
    )

    assert [(r.name, r.value) for r in statistics_fact(part).rows] == [
        ("female lower fence", "1.0"),
        ("female q1", "2.0"),
        ("female median", "3.5"),
        ("female q3", "4.0"),
        ("female upper fence", "6.0"),
        ("female outliers", "1"),
    ]


def test_a_stat_reference_renders_the_value_it_names() -> None:
    facts = TurnFacts(statistics=[pca_fact(_PCA), statistics_fact(_TWO_BY_TWO)])
    prose = (
        f"The first component explains [stat:{_PCA_ID}.PC1] of the variance; the "
        "odds ratio is [stat:stat_9f2c4e1a.odds ratio] "
        "(p [stat:stat_9f2c4e1a.odds ratio p-value])."
    )

    assert prose_faults(prose, facts) == []
    assert render_reply(prose, facts) == (
        "The first component explains 41.2% of the variance; the odds ratio "
        "is 3.25 (p 0.0412)."
    )


def test_a_bare_statistic_is_a_fault_that_names_its_reference() -> None:
    facts = TurnFacts(statistics=[pca_fact(_PCA)])

    assert prose_faults("The first component explains 41.2% of it.", facts) == [
        ProseFault(token="41.2%", kind="number", references=(f"[stat:{_PCA_ID}.PC1]",))
    ]


def test_a_stat_reference_to_a_row_the_statistic_lacks_is_unheld() -> None:
    facts = TurnFacts(statistics=[pca_fact(_PCA)])

    assert prose_faults(f"[stat:{_PCA_ID}.PC3]", facts) == [
        ProseFault(token=f"[stat:{_PCA_ID}.PC3]", kind="unheld_reference")
    ]


def test_the_facts_list_each_statistic_under_its_title() -> None:
    facts = TurnFacts(statistics=[statistics_fact(_TWO_BY_TWO)])

    assert facts.lines() == [
        "Two-by-two table of infection status by sex",
        "odds ratio: 3.25",
        "odds ratio p-value: 0.0412",
        "odds ratio confidence interval: 1.05-10.06",
    ]
    assert facts.empty() is True


def test_an_axis_without_a_stated_variance_keeps_its_label() -> None:
    """A component whose label states no share is referenced by the label."""
    unlabeled = _PCA.model_copy(
        update={
            "axes": [
                EdaPcaAxis(variable_id="PC1", display_name="PC 1"),
                EdaPcaAxis(variable_id="PC2", display_name="PC2 (17.8%)"),
            ]
        }
    )

    assert [r.value for r in pca_fact(unlabeled).rows[:2]] == ["PC 1", "17.8%"]


_SEXES = _PCA.model_copy(
    update={
        "axes": [
            EdaPcaAxis(variable_id="PC1", display_name="PC 1 (94.26% variance)"),
            EdaPcaAxis(variable_id="PC2", display_name="PC 2 (3.09% variance)"),
        ],
        "series": [
            EdaPcaSeries(
                label="Female gametocytes",
                x=[79.3054615368446, 81.1705703065748, 86.5176389923973],
                y=[5.91792635563997, 8.22802619966753, -17.0296652427709],
                sample_ids=["F1", "F2", "F3"],
            ),
            EdaPcaSeries(
                label="Male gametocytes",
                x=[-79.9466671333113, -70.4438849147234, -96.6031187877825],
                y=[7.54157414782451, 18.6981295405845, -23.3559910009457],
                sample_ids=["M1", "M2", "M3"],
            ),
        ],
    }
)


def test_a_reply_states_where_each_group_sits() -> None:
    facts = TurnFacts(statistics=[pca_fact(_SEXES)])
    prose = (
        f"Female samples sit at [stat:{_PCA_ID}.Female gametocytes PC1 range] and "
        f"male samples at [stat:{_PCA_ID}.Male gametocytes PC1 range] on PC1, which "
        f"explains [stat:{_PCA_ID}.PC1]."
    )

    assert prose_faults(prose, facts) == []
    assert render_reply(prose, facts) == (
        "Female samples sit at 79.31 to 86.52 and male samples at -96.6 to -70.44 "
        "on PC1, which explains 94.26%."
    )


def test_what_separates_is_a_statement_no_reference_names() -> None:
    fact = pca_fact(_SEXES)

    assert fact.statements == [
        (
            "PC1 separates Female gametocytes from Male gametocytes; their ranges "
            "on PC1 do not overlap."
        ),
        "PC2 separates no pair of groups; every pair's ranges on PC2 overlap.",
    ]
    assert fact.lines()[-2:] == fact.statements
    assert [r.name for r in fact.rows if "separat" in r.name] == []


def test_a_bare_group_position_is_a_fault_that_names_its_reference() -> None:
    facts = TurnFacts(statistics=[pca_fact(_SEXES)])

    assert prose_faults("Male samples reach -96.6 on PC1.", facts) == [
        ProseFault(
            token="96.6",
            kind="number",
            references=(f"[stat:{_PCA_ID}.Male gametocytes PC1 range]",),
        )
    ]


def test_one_group_has_no_pairs_and_one_sample_has_no_span() -> None:
    alone = _PCA.model_copy(
        update={
            "series": [
                EdaPcaSeries(label="study", x=[2.5], y=[-0.125], sample_ids=["S1"])
            ]
        }
    )

    fact = pca_fact(alone)

    assert [(r.name, r.value) for r in fact.rows[4:]] == [
        ("study PC1 range", "2.5"),
        ("study PC1 mean", "2.5"),
        ("study PC2 range", "-0.125"),
        ("study PC2 mean", "-0.125"),
    ]
    assert fact.statements == []


def test_each_pair_a_component_separates_is_a_statement_of_its_own() -> None:
    three = _PCA.model_copy(
        update={
            "series": [
                EdaPcaSeries(
                    label="a", x=[0.5, 1.0], y=[0.0, 2.0], sample_ids=["1", "2"]
                ),
                EdaPcaSeries(
                    label="b", x=[5.0, 6.0], y=[1.0, 3.0], sample_ids=["3", "4"]
                ),
                EdaPcaSeries(
                    label="c", x=[9.0, 9.5], y=[0.5, 1.5], sample_ids=["5", "6"]
                ),
            ]
        }
    )

    assert pca_fact(three).statements == [
        "PC1 separates a from b; their ranges on PC1 do not overlap.",
        "PC1 separates a from c; their ranges on PC1 do not overlap.",
        "PC1 separates b from c; their ranges on PC1 do not overlap.",
        "PC2 separates no pair of groups; every pair's ranges on PC2 overlap.",
    ]
