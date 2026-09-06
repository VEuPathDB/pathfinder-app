from __future__ import annotations

from veupathdb.eda.models import EdaStudyOverview

from pathfinder.services.eda.catalog import study_cache_key


def _study(*, sha: str, modified: str) -> EdaStudyOverview:
    return EdaStudyOverview(
        id="STUDY_x",
        dataset_id="DS_x",
        sha1hash=sha,
        source_type="curated" if sha else "user_submitted",
        display_name="x",
        last_modified=modified,
    )


def test_a_curated_study_keys_on_its_content_hash() -> None:
    key = study_cache_key(
        base_url="https://plasmodb.org/eda",
        study=_study(sha="abc123", modified="2026-05-27T20:00:00-04:00"),
    )
    assert "abc123" in key
    assert "2026-05-27" not in key


def test_a_user_study_keys_on_last_modified_because_the_hash_is_empty() -> None:
    """All 12 user_submitted studies live carry sha1hash == ""."""
    key = study_cache_key(
        base_url="https://plasmodb.org/eda",
        study=_study(sha="", modified="2026-05-27T20:00:00-04:00"),
    )
    assert "2026-05-27T20:00:00-04:00" in key


def test_the_base_url_is_part_of_the_key() -> None:
    """A study id is only meaningful together with its deployment."""
    plasmo = study_cache_key(
        base_url="https://plasmodb.org/eda",
        study=_study(sha="abc123", modified="m"),
    )
    clinepi = study_cache_key(
        base_url="https://clinepidb.org/eda",
        study=_study(sha="abc123", modified="m"),
    )
    assert plasmo != clinepi


def test_a_user_study_with_a_new_last_modified_gets_a_new_key() -> None:
    first = study_cache_key(
        base_url="b", study=_study(sha="", modified="2026-05-27T20:00:00-04:00")
    )
    second = study_cache_key(
        base_url="b", study=_study(sha="", modified="2026-05-28T20:00:00-04:00")
    )
    assert first != second
