from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS, LEAD_MODE_LINE


def test_the_lead_reads_the_mode_line_once() -> None:
    assert LEAD_INSTRUCTIONS.count(LEAD_MODE_LINE.strip()) == 1
