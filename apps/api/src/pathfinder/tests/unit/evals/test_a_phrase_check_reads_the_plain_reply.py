from __future__ import annotations

from pathlib import Path

import pytest

from pathfinder.devtools.gates import Gate
from pathfinder.domain.written_links import plain_markdown, unescaped_markdown
from pathfinder.evals.case import CaseProvenance, EvalCase, ExpectedOutcome, GatePlan
from pathfinder.evals.run_directory import observed_from_run_directory
from pathfinder.evals.scoring import ObservedOutcome, score_case

_PLAIN = "You declined the last offer. Say what to change, or ask me to offer it again."
_ESCAPED = (
    r"You declined the last offer\. Say what to change\, "
    r"or ask me to offer it again\."
)


def _case(expected: ExpectedOutcome) -> EvalCase:
    return EvalCase(
        name="a-case",
        turns=["Offer it."],
        site_id="plasmodb",
        assistant_id="pathfinder",
        rationale="pins a phrase",
        expected=expected,
        provenance=CaseProvenance(
            site="plasmodb",
            assistant="pathfinder",
            origin="uat-flow",
            reference="a-flow.md",
            added_at="2026-11-03",
        ),
        gates=GatePlan(policy="auto"),
    )


def _observed_run(root: Path, *replies: str) -> ObservedOutcome:
    for number, reply in enumerate(replies, 1):
        turn = root / f"turn-{number}"
        turn.mkdir()
        (turn / "transcript.md").write_text(
            f"# Turn\n\n## Reply\n\n{reply}\n\n## Assumed\n\n"
        )
        (turn / "gate.json").write_text(
            Gate(kind="none").model_dump_json(by_alias=True)
        )
    return observed_from_run_directory(root)


@pytest.mark.parametrize(
    "text",
    [
        _PLAIN,
        "PF3D7_1133400 (stated): 6,123 genes before this turn's edit",
        "a literal back\\slash and a \\. mark",
        '[compare:1] <b> & ~ | ` { } ^ $ # * + = ? ! @ / ; : " - %',
    ],
)
def test_the_reverse_of_the_escape_returns_the_text(text: str) -> None:
    assert unescaped_markdown(plain_markdown(text)) == text


def test_the_escape_is_removed_once() -> None:
    assert unescaped_markdown(plain_markdown(plain_markdown("a.b"))) == r"a\.b"


def test_a_written_link_and_a_letter_keep_their_marks() -> None:
    linked = r"[PF3D7_1133400](https://x.org/a_b) \d stays"

    assert unescaped_markdown(linked) == linked


def test_a_run_directory_reads_each_turn_as_its_plain_text(tmp_path: Path) -> None:
    observed = _observed_run(tmp_path, r"Built\.", _ESCAPED)

    assert observed.reply_text == _PLAIN
    assert observed.turn_replies == ["Built.", _PLAIN]


def test_a_mentioned_phrase_with_escaped_punctuation_matches(tmp_path: Path) -> None:
    observed = _observed_run(tmp_path, _ESCAPED)

    score = score_case(
        _case(ExpectedOutcome(builds_strategy=None, reply_mentions=[_PLAIN])),
        observed,
    )

    assert score.passed is True


@pytest.mark.parametrize(
    ("phrase", "reply"),
    [
        ("'Trypanosomatidae' is withdrawn", r"\'Trypanosomatidae\' is withdrawn\."),
        (
            "6,123 genes before this turn's edit",
            r"6\,123 genes before this turn\'s edit",
        ),
        ("step_", r"It read step\_12\."),
        ("signal peptide", r"A signal\-peptide search\."),
    ],
)
def test_an_omitted_phrase_the_reply_holds_fails(
    tmp_path: Path, phrase: str, reply: str
) -> None:
    observed = _observed_run(tmp_path, reply)

    score = score_case(
        _case(ExpectedOutcome(builds_strategy=None, reply_omits=[phrase])), observed
    )

    assert [d.field for d in score.differences] == ["replyOmits"]
    assert score.passed is False


def test_a_per_turn_omitted_phrase_the_reply_holds_fails(tmp_path: Path) -> None:
    observed = _observed_run(tmp_path, r"\[count:3\] genes\.", "Done.")

    score = score_case(
        _case(ExpectedOutcome(builds_strategy=None, turn_reply_omits={0: ["[count:"]})),
        observed,
    )

    assert [d.field for d in score.differences] == ["turnReplyOmits.0"]
