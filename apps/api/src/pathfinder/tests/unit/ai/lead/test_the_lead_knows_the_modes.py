from pathlib import Path

from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS, LEAD_MODE_LINE

LEAD_INSTRUCTIONS_ON_MAIN = (
    Path(__file__).resolve().parents[3] / "fixtures" / "lead_instructions_main.txt"
).read_text(encoding="utf-8")


def test_the_lead_reads_the_mode_line_once() -> None:
    assert LEAD_INSTRUCTIONS.count(LEAD_MODE_LINE.strip()) == 1


def test_the_mode_line_is_the_only_change() -> None:
    assert LEAD_INSTRUCTIONS.replace(LEAD_MODE_LINE, "", 1) == LEAD_INSTRUCTIONS_ON_MAIN
