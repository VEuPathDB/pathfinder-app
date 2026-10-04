"""A card covers a stated requirement by key or by the strategy holding it, and a
combination when it covers each term."""

from __future__ import annotations

from veupathdb.domain.parameters import StringValue

from pathfinder.domain.strategy.card_coverage import (
    held_by_the_spec,
    uncovered_requirements,
)
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.data_marks import DataMarks
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)


def _stated(kind: ConstraintKind, value: str) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        label=value,
        source=ConstraintSource.USER_EXPLICIT,
    )


_PHRASE = _stated(ConstraintKind.OTHER, "GPI anchored")
_VSG = _stated(ConstraintKind.OTHER, "variant surface glycoprotein")
_UNION = _stated(
    ConstraintKind.COMBINATION, "GPI anchored OR variant surface glycoprotein"
)
_HELD = [_PHRASE, _VSG, _UNION]


def _spec(expression: str, *, record_type: str = "transcript") -> OperationalSpec:
    step = Criterion(
        id="step_text",
        text="surface proteins",
        search_name="GenesByText",
        resolved_params={
            "text_expression": BoundValue(
                value=StringValue(value=expression), source="stated"
            )
        },
    )
    return OperationalSpec(record_type=record_type, criteria=[step])


def test_a_combination_is_covered_when_each_term_is() -> None:
    left = uncovered_requirements(
        _HELD, named={_PHRASE.key, _VSG.key}, held=_HELD, spec=None
    )

    assert left == []


def test_a_combination_with_an_uncovered_term_is_left() -> None:
    left = uncovered_requirements(_HELD, named={_PHRASE.key}, held=_HELD, spec=None)

    assert [c.key for c in left] == [_VSG.key, _UNION.key]


def test_a_term_a_step_already_searches_covers_its_side() -> None:
    left = uncovered_requirements(
        _HELD, named={_VSG.key}, held=_HELD, spec=_spec("GPI anchored")
    )

    assert left == []


def test_genes_are_held_by_a_transcript_strategy_and_not_by_a_pathway_one() -> None:
    genes = _stated(ConstraintKind.RECORD_TYPE, "genes")

    assert (
        held_by_the_spec(genes, _spec("kinase")),
        held_by_the_spec(genes, _spec("kinase", record_type="pathway")),
    ) == (True, False)


def test_a_data_type_the_spec_grounds_is_held_whatever_the_words() -> None:
    rnaseq = _stated(ConstraintKind.DATA_TYPE, "RNA-Seq")
    step = Criterion(
        id="step_expr",
        text="expressed in schizonts",
        search_name="GenesByRNASeqpfal3D7_Otto_Time_Series_RSRC",
    )
    spec = OperationalSpec(record_type="transcript", criteria=[step])

    marks = DataMarks(searches={"GenesByRNASeqpfal3D7_Otto_Time_Series_RSRC": "RNASeq"})

    assert (
        held_by_the_spec(rnaseq, spec, marks=marks),
        held_by_the_spec(rnaseq, _spec("kinase"), marks=marks),
    ) == (
        True,
        False,
    )
