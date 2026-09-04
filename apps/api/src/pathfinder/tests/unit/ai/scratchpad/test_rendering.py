from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pathfinder.ai.scratchpad.rendering import render_scratchpad_for_phase
from pathfinder.domain.scratchpad.models import Note


def _note(
    *,
    nid: str,
    title: str,
    summary: str,
    pinned: bool = False,
    body_len: int = 40,
) -> Note:
    now = datetime.now(UTC)
    return Note(
        id=nid,
        conversation_id=uuid4(),
        title=title,
        summary=summary,
        body="x" * body_len,
        tags=[],
        pinned=pinned,
        body_tokens=body_len // 4,
        created_at=now,
        updated_at=now,
    )


class TestEmptyState:
    def test_phase_empty_shows_hint_and_rule(self) -> None:
        out = render_scratchpad_for_phase([], total_count=0)
        assert "## Scratchpad (empty)" in out
        assert "Rule:" in out


class TestPopulated:
    def test_phase_lists_pinned_and_recent(self) -> None:
        notes = [
            _note(
                nid="n-aaa111", title="Pinned A", summary="pinned summary", pinned=True
            ),
            _note(nid="n-bbb222", title="Recent A", summary="recent summary"),
        ]
        out = render_scratchpad_for_phase(notes, total_count=2)
        assert "n-aaa111" in out
        assert "n-bbb222" in out
        assert "Pinned A" in out
        assert "Recent A" in out
        assert "Rule:" in out

    def test_total_count_shown(self) -> None:
        notes = [_note(nid="n-x", title="T", summary="S")]
        out = render_scratchpad_for_phase(notes, total_count=7)
        # "7 notes" or "(7 notes" format
        assert "7" in out


class TestBudget:
    def test_drops_oldest_non_pinned_when_over_budget(self) -> None:
        # Craft 5 non-pinned notes; budget forces drops.
        notes = [_note(nid=f"n-{i:06x}", title=f"T{i}", summary="s") for i in range(5)]
        out = render_scratchpad_for_phase(notes, total_count=5, budget_chars=300)
        # Must not include all 5 — budget forces a drop.
        included = sum(1 for i in range(5) if f"T{i}" in out)
        assert included < 5

    def test_pinned_never_dropped_by_budget(self) -> None:
        notes = [
            _note(nid="n-pin", title="PINNED_KEEP", summary="p", pinned=True),
            *[_note(nid=f"n-{i:06x}", title=f"T{i}", summary="s") for i in range(5)],
        ]
        out = render_scratchpad_for_phase(notes, total_count=6, budget_chars=300)
        assert "PINNED_KEEP" in out
