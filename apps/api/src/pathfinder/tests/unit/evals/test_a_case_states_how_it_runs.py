"""A case names its effort, whether it stops at the last gate, and its attached files."""

from __future__ import annotations

import datetime
import json

import pytest
from pydantic import ValidationError

from pathfinder.ai.lead.intent_gate import DECLINED_OFFER_REFUSAL
from pathfinder.evals.case import (
    CaseProvenance,
    EvalCase,
    GateAnswer,
    GatePlan,
    RecordedCount,
)
from pathfinder.evals.store import (
    ATTACHMENTS_DIR,
    attachment_paths,
    load_case,
    load_corpus,
)


def _raw(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "name": "uat-c12-plasmodb",
        "turns": ["Use these genes as my positive controls."],
        "siteId": "plasmodb",
        "assistantId": "pathfinder",
        "rationale": "pins the attached list",
        "expected": {"buildsStrategy": False},
        "provenance": {
            "site": "plasmodb",
            "assistant": "pathfinder",
            "origin": "cataloged-failure",
            "addedAt": "2026-09-25",
            "reference": "uat/flows-composer.md#c12",
        },
        "gates": {"policy": "stop"},
    }
    raw.update(overrides)
    return raw


def test_a_case_runs_at_the_tier_effort_and_attaches_nothing() -> None:
    case = EvalCase.model_validate(_raw())

    assert (case.effort, case.gates, case.attachments) == (
        None,
        GatePlan(policy="stop"),
        {},
    )


def test_the_fields_read_from_the_corpus_json() -> None:
    raw = _raw(
        effort="high",
        gates={"policy": "stop"},
        attachments={"0": ["controls.csv"]},
        expected={
            "buildsStrategy": True,
            "countsInGenes": True,
            "endsOn": "approval",
            "rootCount": {
                "count": 116,
                "build": "71",
                "measuredOn": "2026-09-24",
            },
        },
    )

    case = EvalCase.model_validate_json(json.dumps(raw))

    assert (case.effort, case.gates, case.attachments) == (
        "high",
        GatePlan(policy="stop"),
        {0: ["controls.csv"]},
    )
    assert (
        case.expected.counts_in_genes,
        case.expected.ends_on,
        case.expected.root_count,
    ) == (
        True,
        "approval",
        RecordedCount(count=116, build="71", measured_on=datetime.date(2026, 9, 24)),
    )


@pytest.mark.parametrize("name", ["uat-s1-fungidb", "uat-s1-toxodb"])
def test_a_shipped_case_holds_the_count_unit_and_forbids_no_bare_word(
    name: str,
) -> None:
    expected = load_case(name).expected

    assert (expected.counts_in_genes, expected.reply_omits) == (True, [])


def test_the_shipped_cases_that_hold_the_count_unit() -> None:
    held = [c.name for c in load_corpus() if c.expected.counts_in_genes is True]

    assert len(held) == 52
    assert [name for name in held if not name.startswith("uat-")] == []


def test_an_attachment_on_a_turn_the_case_does_not_have_is_refused() -> None:
    with pytest.raises(ValidationError, match="turn 1"):
        EvalCase.model_validate(_raw(attachments={1: ["controls.csv"]}))


def test_a_gate_the_runner_does_not_read_is_refused() -> None:
    with pytest.raises(ValidationError, match="endsOn"):
        EvalCase.model_validate(
            _raw(expected={"buildsStrategy": False, "endsOn": "durable"})
        )


def test_an_attachment_resolves_under_the_corpus_files() -> None:
    case = EvalCase.model_validate(_raw(attachments={0: ["controls.csv"]}))

    assert (attachment_paths(case, 0), attachment_paths(case, 1)) == (
        [ATTACHMENTS_DIR / "controls.csv"],
        [],
    )


def test_every_shipped_attachment_is_on_disk() -> None:
    missing = [
        f"{case.name}: {path.name}"
        for case in load_corpus()
        for turn in case.attachments
        for path in attachment_paths(case, turn)
        if not path.is_file()
    ]

    assert missing == []


def test_every_uat_case_is_named_for_its_flow_and_its_site() -> None:
    misnamed = [
        case.name
        for case in load_corpus()
        if case.name.startswith("uat-")
        and not (
            case.name.endswith(f"-{case.site_id}")
            and case.provenance.site == case.site_id
            and case.provenance.reference.startswith("uat/flows-")
        )
    ]

    assert misnamed == []


def test_a_comment_goes_with_a_no_only() -> None:
    with pytest.raises(ValidationError, match="comment"):
        GateAnswer(card="propose_changes", turn=0, accept=True, comment="looks right")


def test_the_v5_case_says_yes_to_the_run_and_no_to_the_offer() -> None:
    case = load_case("uat-v5-plasmodb")

    assert (
        [turn.splitlines()[0] for turn in case.turns],
        case.gates,
        case.expected.builds_strategy,
    ) == (
        [
            "Find me a strategy that separates these controls, in exact mode.",
            "What did you offer me?",
        ],
        GatePlan(
            policy="leave",
            answers=[
                GateAnswer(card="separate_controls", turn=0),
                GateAnswer(
                    card="adopt_separating_strategy",
                    turn=0,
                    accept=False,
                    comment="Too broad for a vaccine screen.",
                ),
            ],
        ),
        False,
    )


def test_a_recorded_count_names_a_real_date() -> None:
    with pytest.raises(ValidationError, match="measuredOn"):
        RecordedCount.model_validate(
            {"count": 116, "build": "71", "measuredOn": "the day after the release"}
        )


def test_a_question_card_answer_picks_options_and_says_nothing_else() -> None:
    picked = GateAnswer(card="consult_user", turn=0, picks=["portal"])
    refused: list[str] = []
    for raw in (
        {"card": "consult_user", "turn": 0, "picks": ["portal"], "accept": False},
        {
            "card": "consult_user",
            "turn": 0,
            "picks": ["portal"],
            "accept": False,
            "comment": "no",
        },
    ):
        try:
            GateAnswer.model_validate(raw)
        except ValidationError as error:
            refused.append(error.errors()[0]["msg"])

    assert (picked.accept, picked.picks, len(refused)) == (True, ["portal"], 2)


def test_a_turn_can_open_a_new_conversation_for_the_same_researcher() -> None:
    case = EvalCase.model_validate(
        _raw(
            turns=["remember this", "what do I prefer?"],
            newConversationBefore=[1],
            gates={"policy": "leave"},
        )
    )

    assert case.new_conversation_before == [1]


@pytest.mark.parametrize("turn", [0, 2])
def test_a_new_conversation_starts_before_a_later_turn_of_the_case(turn: int) -> None:
    with pytest.raises(ValidationError, match="new conversation"):
        EvalCase.model_validate(
            _raw(
                turns=["remember this", "what do I prefer?"],
                newConversationBefore=[turn],
                gates={"policy": "leave"},
            )
        )


def test_the_n7_case_declines_the_offer_then_sends_a_bare_yes() -> None:
    case = load_case("uat-n7-plasmodb")

    assert (case.turns[-1], case.gates.answers) == (
        "yes",
        [
            GateAnswer(
                card="propose_changes",
                turn=1,
                accept=False,
                comment="Not now: a kinase filter is too narrow for what I need.",
            )
        ],
    )


def test_the_n8_case_picks_the_portal_and_the_m6_case_asks_in_a_new_thread() -> None:
    n8 = load_case("uat-n8-plasmodb")
    m6 = load_case("uat-m6-plasmodb")

    assert (n8.gates.answers, m6.new_conversation_before) == (
        [GateAnswer(card="consult_user", turn=1, picks=["portal"])],
        [1],
    )


def test_a_uat_flow_case_names_its_flow_and_no_staging_row() -> None:
    refused: list[str] = []
    for raw in (
        {"origin": "uat-flow"},
        {
            "origin": "uat-flow",
            "reference": "uat/flows-verification.md#v5",
            "stagingId": "0f0f",
        },
    ):
        try:
            CaseProvenance.model_validate(
                {
                    "site": "plasmodb",
                    "assistant": "pathfinder",
                    "addedAt": "2026-09-25",
                    **raw,
                }
            )
        except ValidationError as error:
            refused.append(str(error.errors()[0]["msg"]))

    assert refused == [
        "Value error, a UAT case names the flow it was written from",
        "Value error, a UAT case came from no staging row",
    ]


def test_every_uat_case_arrived_from_a_uat_flow() -> None:
    origins = {
        case.provenance.origin for case in load_corpus() if case.name.startswith("uat-")
    }

    assert origins == {"uat-flow"}


def test_a_uat_case_asserts_no_prose_the_model_words_its_own_way() -> None:
    phrases = {
        case.name: case.expected.reply_mentions
        for case in load_corpus()
        if case.name.startswith("uat-")
        and not case.name.startswith("uat-dry-")
        and case.expected.reply_mentions
    }

    assert phrases == {
        "uat-c13-plasmodb": ["PF3D7_0709000", "PF3D7_1133400", "PF3D7_0102600"],
        "uat-c14-plasmodb": ["PF3D7_0709000", "PF3D7_1133400", "PF3D7_0102600"],
        "uat-m6-plasmodb": ["Su et al"],
        "uat-n7-plasmodb": [DECLINED_OFFER_REFUSAL],
        "uat-n8-plasmodb": ["portal"],
        "uat-s15-plasmodb": ["heat shock protein"],
        "uat-v2-plasmodb": ["52 of 80", "2 of 40"],
        "uat-x6-vectorbase": ["portal"],
    }


def test_a_uat_case_holds_the_check_to_zero_unmet_rows_not_a_met_count() -> None:
    counted = {
        case.name: (case.expected.met_requirements, case.expected.unmet_requirements)
        for case in load_corpus()
        if case.name.startswith("uat-")
        and (
            case.expected.met_requirements is not None
            or case.expected.unmet_requirements is not None
        )
    }

    assert counted == {
        **{
            f"uat-s2-{site}": (None, 0)
            for site in ("fungidb", "plasmodb", "toxodb", "vectorbase", "veupathdb")
        },
        "uat-dry-c-piroplasmadb": (None, 0),
    }


def test_the_v2_case_reads_the_control_counts_in_the_reply_and_no_verdict() -> None:
    case = load_case("uat-v2-plasmodb")

    assert (
        case.expected.verified,
        case.expected.reply_mentions,
        case.rationale,
    ) == (
        None,
        ["52 of 80", "2 of 40"],
        (
            "The reply states the recovered positives and the returned negatives "
            "with their counts."
        ),
    )


def test_the_v4_case_stops_at_the_run_approval_on_its_first_message() -> None:
    case = load_case("uat-v4-plasmodb")

    assert (
        len(case.turns),
        case.turns[0].splitlines()[0],
        case.gates,
        case.expected.ends_on,
        case.expected.builds_strategy,
    ) == (
        1,
        "Find me a strategy that separates these controls, in exact mode.",
        GatePlan(policy="stop"),
        "approval",
        False,
    )


def test_the_s5_toxodb_case_carries_the_seed_to_neospora_without_synteny() -> None:
    case = load_case("uat-s5-toxodb")
    expected = case.expected

    assert (
        case.turns[1],
        expected.parameters,
        expected.root_count,
        case.provenance.reference,
        "Neospora caninum Liverpool" in case.rationale,
    ) == (
        "Carry these to their orthologs in Neospora caninum Liverpool.",
        {
            "GenesByOrthologs": {
                "organism": "Neospora caninum Liverpool",
                "isSyntenic": "no",
            }
        },
        RecordedCount(count=145, build="71", measured_on=datetime.date(2026, 9, 24)),
        "uat/flows-strategy-standard.md#s5 uat/findings.md#fnd-1",
        True,
    )


def test_the_n1_case_answers_the_card_and_builds_the_three_criteria() -> None:
    case = load_case("uat-n1-plasmodb")
    expected = case.expected

    assert (
        case.gates.answers,
        expected.builds_strategy,
        expected.root_operator,
        expected.step_count,
        expected.parameters,
        expected.verified,
    ) == (
        [GateAnswer(card="consult_user", turn=0, picks=[])],
        True,
        "INTERSECT",
        None,
        {"GenesByOrthologPattern": {"excluded_species": "hsap"}},
        None,
    )


@pytest.mark.parametrize(
    ("name", "stated"),
    [
        ("uat-core-d-microsporidiadb", ["66 genes", "9 genes", "57 genes"]),
        ("uat-core-a-cryptodb", ["84 genes", "82 genes"]),
    ],
)
def test_a_count_case_states_the_rendered_counts_and_no_reference(
    name: str, stated: list[str]
) -> None:
    expected = load_case(name).expected

    assert expected.turn_reply_mentions == {1: stated}
    assert all(omitted.startswith("[") for omitted in expected.turn_reply_omits[1])
