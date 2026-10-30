"""The sentence and share fields the tool server marks in its own answer types render as sentence rows and percentages."""

from __future__ import annotations

from veupathdb_mcp.audit import IntronAudit

from pathfinder.domain.statistic_facts import StatisticRowFact
from pathfinder.domain.statistic_rows import model_rows, schema_rows
from pathfinder.services.audit.investigation import rate_with_interval


def test_the_intron_audits_free_text_fields_are_sentences() -> None:
    rows = schema_rows(
        IntronAudit,
        {
            "reason": "No junction track was read for this organism.",
            "correctionReason": "The replacement junction keeps the frame.",
            "orthologs": {"reason": "No ortholog protein was read."},
        },
    )

    assert rows == [
        StatisticRowFact(
            name="reason", value="No junction track was read for this organism."
        ),
        StatisticRowFact(
            name="correctionReason", value="The replacement junction keeps the frame."
        ),
        StatisticRowFact(
            name="orthologs.reason", value="No ortholog protein was read."
        ),
    ]


def test_a_rates_bounds_render_as_percentages() -> None:
    rows = {row.name: row.value for row in model_rows(rate_with_interval(7, 9, 1))}

    assert rows == {
        "confirmed": "7",
        "checked": "9",
        "unresolved": "1",
        "rate": "77.8%",
        "low": "45.3%",
        "high": "93.7%",
        "floor": "70%",
        "ceiling": "80%",
    }
