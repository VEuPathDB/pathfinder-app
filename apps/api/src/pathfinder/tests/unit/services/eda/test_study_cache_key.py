"""A curated study's metadata is cached under its deployment, its id and its
content hash."""

from __future__ import annotations

from veupathdb.eda import EdaStudyOverview

from pathfinder.services.eda.catalog import study_cache_key


def _study(sha: str) -> EdaStudyOverview:
    return EdaStudyOverview(
        id="STUDY_x",
        dataset_id="DS_x",
        sha1hash=sha,
        source_type="curated",
        display_name="x",
        last_modified="2026-05-27T20:00:00-04:00",
    )


def test_a_curated_study_keys_on_its_content_hash() -> None:
    key = study_cache_key(base_url="https://plasmodb.org/eda", study=_study("abc123"))

    assert key == "https://plasmodb.org/eda|STUDY_x|abc123"


def test_a_new_content_hash_is_a_new_key() -> None:
    assert study_cache_key(base_url="b", study=_study("abc123")) != study_cache_key(
        base_url="b", study=_study("def456")
    )


def test_the_base_url_is_part_of_the_key() -> None:
    """A study id is only meaningful together with its deployment."""
    plasmo = study_cache_key(base_url="https://plasmodb.org/eda", study=_study("abc"))
    clinepi = study_cache_key(base_url="https://clinepidb.org/eda", study=_study("abc"))

    assert plasmo != clinepi
