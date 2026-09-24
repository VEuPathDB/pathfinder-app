"""The first-pass redaction that runs before anything is staged."""

from __future__ import annotations

import pytest

from pathfinder.evals.redaction import (
    RedactionFailedError,
    assert_redacted,
    redact_text,
)


def test_an_email_address_is_replaced() -> None:
    assert redact_text("write to ada@example.org please") == (
        "write to [redacted-email] please"
    )


def test_several_addresses_are_all_replaced() -> None:
    redacted = redact_text("a@b.org and c.d+tag@sub.example.co.uk")

    assert redacted == "[redacted-email] and [redacted-email]"


def test_a_url_with_a_userinfo_part_loses_the_credential() -> None:
    assert redact_text("see https://ada:secret@plasmodb.org/x") == (
        "see https://[redacted-credential]@plasmodb.org/x"
    )


def test_a_gene_identifier_survives() -> None:
    """Redaction must not eat the science: gene ids carry digits and an underscore."""
    text = "PF3D7_0709000 and GO:0004672 at 90th percentile"

    assert redact_text(text) == text


def test_a_digit_run_survives() -> None:
    """Counts, thresholds and WDK ids are digit runs, so no digit rule can fire."""
    assert redact_text("strategy 330423363 root 132 genes") == (
        "strategy 330423363 root 132 genes"
    )


def test_assert_redacted_accepts_clean_text() -> None:
    assert_redacted("kinases in P. falciparum 3D7")


def test_assert_redacted_refuses_a_surviving_address() -> None:
    with pytest.raises(RedactionFailedError, match="email"):
        assert_redacted("contact ada@example.org")


def test_assert_redacted_refuses_a_surviving_credential() -> None:
    with pytest.raises(RedactionFailedError, match="credential"):
        assert_redacted("https://ada:secret@plasmodb.org/x")


def test_redacted_text_passes_the_check() -> None:
    text = "see https://ada:secret@plasmodb.org/x or write to ada@example.org"

    assert assert_redacted(redact_text(text)) is True
