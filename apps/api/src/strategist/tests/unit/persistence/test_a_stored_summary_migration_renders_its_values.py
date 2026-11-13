import importlib.util
import pathlib
from typing import Any

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[5]
    / "alembic"
    / "versions"
    / "2026_10_30_0001_a_synthesis_summary_is_stored_rendered.py"
)

_STORED = {
    "sections": [],
    "headline": [],
    "agreement": {"sampled": 4, "agreed": 3},
    "summary": (
        "The run kept [stat:stat_ad5c5b01.counts.kept] errors, mostly shifted "
        "splice sites [cite:stat_ad5c5b01.headline.0.errorTitle]. "
        "[cite:stat_gone.row]Curators read them first."
    ),
    "facts": [
        {
            "id": "stat_ad5c5b01",
            "kind": "audit_run",
            "title": "Audit run",
            "rows": [
                {"name": "counts.kept", "value": "12", "form": "number"},
                {
                    "name": "headline.0.errorTitle",
                    "value": "Splice site shifted",
                    "form": "word",
                },
            ],
        }
    ],
}


def _rendered() -> Any:
    spec = importlib.util.spec_from_file_location("_summary_migration", _MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.rendered


def test_a_stored_cite_and_stat_render_in_place() -> None:
    assert _rendered()(_STORED)["summary"] == (
        "The run kept 12 errors, mostly shifted splice sites "
        "(Splice site shifted).Curators read them first."
    )


def test_the_stored_facts_are_dropped_and_the_rest_kept() -> None:
    migrated = _rendered()(_STORED)

    assert (sorted(migrated), migrated["agreement"]) == (
        ["agreement", "headline", "sections", "summary"],
        {"sampled": 4, "agreed": 3},
    )
