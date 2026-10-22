"""A question about a free-text or range value offers readings the site can
build, each an option that binds its value under its count."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from veupathdb.domain.parameters import NumberValue, StringValue
from veupathdb.domain.strategy import StrategyStepNode

from pathfinder.domain.caveats import caveats_for
from pathfinder.domain.reading_caveats import ReadingCaveat, reading_line
from pathfinder.domain.strategy.card_answers import spec_with_reading
from pathfinder.domain.strategy.measurement_clauses import measurement_clauses
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import (
    OpenQuestion,
    SlotQuestion,
)
from pathfinder.domain.strategy.readings import (
    AcceptedReading,
    Reading,
    ReadValues,
    reading_problems,
)
from pathfinder.domain.strategy.spec_replay import (
    criterion_rebound,
    criterion_restated,
)
from pathfinder.domain.value_caveats import assumed_value_caveats

EVERY, SHARE = "PLAS=61T AND TOXO=0T", "PLAS>=55T AND TOXO=0T"
_EXPRESSION = "phyletic_expression"
_SHARE_LABEL = "At least 55 of the 61 genomes (90%)"
_SHARE_CAVEAT = "Keeps groups missing from up to 6 genomes"
_PRESENT = "other:present in all Plasmodium species"


def criterion_with(
    criterion_id: str,
    *,
    measurements: list[Measurement],
    bound: str | None = None,
    accepted: AcceptedReading | None = None,
) -> Criterion:
    return Criterion(
        id=criterion_id,
        text="present in all Plasmodium species, absent from Toxoplasma",
        search_name="GroupsByPhyleticPattern",
        resolved_params={}
        if bound is None
        else {_EXPRESSION: BoundValue(value=StringValue(value=bound), source="chosen")},
        param_display_names={_EXPRESSION: "Expression"},
        measurements=measurements,
        result_count=None if bound is None else 395,
        accepted_reading=accepted,
    )


def _counted() -> list[Measurement]:
    return [
        Measurement(kind="reading", param=_EXPRESSION, reading=EVERY, count=395),
        Measurement(kind="reading", param=_EXPRESSION, reading=SHARE, count=1088),
    ]


def _question(**fields: object) -> SlotQuestion:
    return SlotQuestion.model_validate(
        {
            "question": "Present in which Plasmodium genomes?",
            "criterionId": "c_plas",
            "paramName": _EXPRESSION,
            "readings": [
                Reading(label="Every one of the 61 genomes", value=EVERY),
                Reading(label=_SHARE_LABEL, value=SHARE, caveat=_SHARE_CAVEAT),
            ],
            "requirements": ["R1"],
        }
        | fields
    )


def _accepted() -> AcceptedReading:
    return AcceptedReading(
        reading=_SHARE_LABEL, caveat=_SHARE_CAVEAT, params={_EXPRESSION: SHARE}
    )


def test_a_reading_becomes_an_option_that_binds_its_value_with_its_count() -> None:
    criterion = criterion_with("c_plas", measurements=_counted())

    typed = _question().typed(criterion, noun="group", replaces=[_PRESENT])

    assert [o.label for o in typed.options] == [
        "Every one of the 61 genomes: 395 groups",
        "At least 55 of the 61 genomes (90%): 1088 groups",
    ]
    assert typed.options[1].binding == ReadValues(
        criterion_id="c_plas",
        params={_EXPRESSION: SHARE},
        reading=_SHARE_LABEL,
        caveat=_SHARE_CAVEAT,
        replaces=[_PRESENT],
    )


def test_a_reading_the_site_did_not_count_is_offered_by_its_label() -> None:
    typed = _question().typed(criterion_with("c_plas", measurements=[]), noun="group")

    assert [o.label for o in typed.options] == [
        "Every one of the 61 genomes",
        _SHARE_LABEL,
    ]


def test_a_picked_reading_carries_the_requirements_it_replaces() -> None:
    read = ReadValues(
        criterion_id="c_plas",
        params={_EXPRESSION: SHARE},
        reading=_SHARE_LABEL,
        caveat=_SHARE_CAVEAT,
        replaces=[_PRESENT],
    )

    assert read.accepted() == _accepted().model_copy(update={"replaces": [_PRESENT]})


def _keyed_readings(*keys: list[str]) -> list[dict[str, str | list[str]]]:
    return [
        {"label": f"At most {n} genomes", "value": f"MICR>=1T AND MICR<={n}T"}
        | ({"requirements": held} if held else {})
        for n, held in zip((3, 5, 10), keys, strict=True)
    ]


def test_keys_written_on_each_reading_are_the_question_s() -> None:
    question = _question(
        readings=_keyed_readings(["R2"], ["R2"], ["R2"]), requirements=[]
    )

    assert question.requirements == ["R2"]
    assert [r.label for r in question.readings] == [
        "At most 3 genomes",
        "At most 5 genomes",
        "At most 10 genomes",
    ]


def test_keys_on_the_question_and_on_its_readings_are_one_list() -> None:
    question = _question(
        readings=_keyed_readings(["R2"], [], ["R3", "R1"]), requirements=["R1"]
    )

    assert question.requirements == ["R1", "R2", "R3"]


def test_a_question_holds_the_keys_it_is_given_and_no_more() -> None:
    assert _question(requirements=[]).requirements == []


def test_a_reading_question_offers_a_choice() -> None:
    criterion = criterion_with("c_plas", measurements=_counted())

    assert _question().offers_a_choice(criterion)


@pytest.mark.parametrize(
    "fields", [{"reading": "x" * 121}, {"reading": "r", "caveat": "x" * 301}]
)
def test_an_accepted_reading_is_held_to_the_card_limits(
    fields: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        AcceptedReading.model_validate({"params": {_EXPRESSION: SHARE}} | fields)


def test_a_recorded_reading_option_keeps_its_binding() -> None:
    criterion = criterion_with("c_plas", measurements=_counted())
    typed = _question().typed(criterion, noun="group")

    assert OpenQuestion.model_validate(typed.model_dump()) == typed


def test_an_accepted_reading_with_a_caveat_is_a_caveat_of_the_spec() -> None:
    spec = OperationalSpec(
        criteria=[
            criterion_with("c_plas", measurements=[], bound=SHARE, accepted=_accepted())
        ]
    )

    assert caveats_for(spec, []) == [
        ReadingCaveat(criterion_id="c_plas", reading=_SHARE_LABEL, caveat=_SHARE_CAVEAT)
    ]
    assert caveats_for(spec, [])[0].sentence == (
        f"Read as '{_SHARE_LABEL}': {_SHARE_CAVEAT}"
    )


def test_an_accepted_reading_without_a_caveat_makes_none() -> None:
    accepted = AcceptedReading(
        reading="Every one of the 61 genomes", params={_EXPRESSION: EVERY}
    )
    spec = OperationalSpec(
        criteria=[
            criterion_with("c_plas", measurements=[], bound=EVERY, accepted=accepted)
        ]
    )

    assert caveats_for(spec, []) == []


def test_a_reading_is_set_on_its_criterion_alone() -> None:
    spec = OperationalSpec(
        criteria=[
            criterion_with("c_plas", measurements=[]),
            criterion_with("c_other", measurements=[]),
        ]
    )

    read = spec_with_reading(spec, "c_plas", _accepted())

    assert [c.accepted_reading for c in read.criteria] == [_accepted(), None]


def test_a_reading_is_held_while_its_criterion_binds_its_values() -> None:
    criterion = criterion_with(
        "c_plas", measurements=[], bound=SHARE, accepted=_accepted()
    )

    restated = criterion_restated(
        criterion, _EXPRESSION, StringValue(value=EVERY), sheet=[], source="card"
    )
    elsewhere = criterion_restated(
        criterion, "other", StringValue(value="x"), sheet=[], source="card"
    )

    assert [c.held_reading for c in (criterion, restated, elsewhere)] == [
        _accepted(),
        None,
        _accepted(),
    ]


def test_a_step_on_another_search_holds_no_reading() -> None:
    criterion = criterion_with(
        "c_plas", measurements=[], bound=SHARE, accepted=_accepted()
    )

    rebound = criterion_rebound(
        criterion,
        StrategyStepNode(
            id="c_plas",
            search_name="GroupsByGenomeCount",
            parameters={"min_taxa": NumberValue(value=4)},
        ),
        None,
    )

    assert (rebound.search_name, rebound.held_reading) == ("GroupsByGenomeCount", None)
    assert caveats_for(OperationalSpec(criteria=[rebound]), []) == []


def test_a_counted_reading_reads_as_one_clause_and_makes_no_value_caveat() -> None:
    criterion = criterion_with(
        "c_plas",
        measurements=[
            Measurement(kind="reading", param=_EXPRESSION, reading=SHARE, count=1088)
        ],
        bound=EVERY,
    )

    assert measurement_clauses(criterion, noun="group") == [
        f"Expression at the chosen {EVERY}: 395 groups; at {SHARE}: 1,088"
    ]
    assert assumed_value_caveats(OperationalSpec(criteria=[criterion])) == []


@pytest.mark.parametrize(
    ("on_question", "on_each_reading", "keys"),
    [
        (None, "R2", ["R2"]),
        ([], [2], ["2"]),
        ("R1", ["R2"], ["R1", "R2"]),
    ],
)
def test_keys_in_another_spelling_are_lifted_as_written(
    on_question: object, on_each_reading: object, keys: list[str]
) -> None:
    question = _question(
        readings=[
            {"label": "Every genome", "value": EVERY, "requirements": on_each_reading},
            {"label": "Most genomes", "value": SHARE, "requirements": on_each_reading},
        ],
        requirements=on_question,
    )

    assert question.requirements == keys


_FOUR = [Reading(label=f"reading {n}", value=f"PLAS>={n}T") for n in range(4)]
_ONE = [Reading(label="Every genome", value=EVERY)]
_TWO = [
    Reading(label="Every genome", value=EVERY),
    Reading(label="Most genomes", value=SHARE),
]


@pytest.mark.parametrize(
    ("readings", "options", "names_a_slot", "changes"),
    [
        (_ONE, [], True, ["offer a second reading, as one reading is no choice"]),
        (
            _TWO,
            ["x", "y"],
            True,
            ["drop its `options`, as a question offers readings or values, never both"],
        ),
        (
            _TWO,
            [],
            False,
            ["name the `criterion_id` and `param_name` its readings set"],
        ),
        (
            [_TWO[0], Reading(label="every genome", value=SHARE)],
            [],
            True,
            ["give each reading its own `label`, as two readings share a label"],
        ),
        (
            [_TWO[0], Reading(label="All of them", value=EVERY)],
            [],
            True,
            ["give each reading its own `value`, as two readings bind one value"],
        ),
        (_FOUR, [], True, ["keep three readings at most, as a card offers no more"]),
        (_TWO, [], True, []),
    ],
)
def test_each_reading_problem_names_its_change(
    readings: list[Reading], options: list[str], names_a_slot: bool, changes: list[str]
) -> None:
    assert (
        reading_problems(readings, options=options, names_a_slot=names_a_slot)
        == changes
    )


def test_a_question_with_a_reading_problem_is_still_a_question() -> None:
    question = SlotQuestion(
        question="q",
        criterion_id="c",
        param_name="p",
        options=["x", "y"],
        readings=_ONE,
    )

    assert (question.options, question.readings) == (["x", "y"], _ONE)


def test_a_reading_label_is_clipped_to_leave_room_for_its_count() -> None:
    assert Reading(label="x" * 91, value=EVERY).label == "x" * 90


def test_a_reading_of_an_unkeyed_question_says_its_pick_replaces_none() -> None:
    criterion = criterion_with("c_plas", measurements=_counted())

    unkeyed = _question(requirements=[]).typed(criterion, noun="group", stated=True)
    keyed = _question().typed(criterion, noun="group", replaces=[_PRESENT], stated=True)
    unstated = _question(requirements=[]).typed(criterion, noun="group")

    assert [
        [
            read.names_no_requirement
            for o in q.options
            if (read := o.offered_reading()) is not None
        ]
        for q in (unkeyed, keyed, unstated)
    ] == [[True, True], [False, False], [False, False]]


def test_a_pick_that_replaces_none_is_a_caveat_and_says_why() -> None:
    held = _accepted().model_copy(update={"names_no_requirement": True})
    criterion = criterion_with("c_plas", measurements=[], bound=SHARE, accepted=held)

    [caveat] = caveats_for(OperationalSpec(criteria=[criterion]), [])

    assert caveat.sentence == (
        f"Read as '{_SHARE_LABEL}': {_SHARE_CAVEAT} The question named no stated "
        "requirement, so the pick replaces none and each requirement it "
        "approximates is still judged on its own words."
    )
    assert reading_line(criterion, held).endswith(
        "The question named no stated requirement, so the pick replaces none and "
        "each requirement it approximates is still judged on its own words."
    )
