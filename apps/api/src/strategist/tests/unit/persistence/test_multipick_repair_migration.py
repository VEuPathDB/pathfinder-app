"""The data repair for multi-pick values stored as the string "[]".

One conversation in the dev database carries
``{"type": "multi-pick-vocabulary", "values": ["[]"]}`` - written while the
type still required a non-empty list, so "nothing selected" was degraded to
the literal ``"[]"``. WDK rejects that term on parameters whose spec allows an
empty value, and the step editor cannot be opened without the read-path
leniency that exists only to tolerate it.

The walk is structural because jsonb normalizes key order and spacing, so
there is no stable textual shape to match on.
"""

from __future__ import annotations

import importlib.util
import pathlib
from typing import Any

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[5]
    / "alembic"
    / "versions"
    / "2026_08_08_0001_repair_empty_multipick_values.py"
)


def _load_repair() -> Any:
    spec = importlib.util.spec_from_file_location("_repair_migration", _MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._repair


class TestRepair:
    def test_the_degraded_empty_selection_becomes_an_empty_list(self) -> None:
        repair = _load_repair()
        node = {"type": "multi-pick-vocabulary", "values": ["[]"]}

        fixed, count = repair(node)

        assert fixed == {"type": "multi-pick-vocabulary", "values": []}
        assert count == 1

    def test_a_real_selection_is_untouched(self) -> None:
        repair = _load_repair()
        node = {"type": "multi-pick-vocabulary", "values": ["Pf3D7"]}

        fixed, count = repair(node)

        assert fixed == node
        assert count == 0

    def test_a_selection_containing_the_literal_alongside_terms_is_left_alone(
        self,
    ) -> None:
        """The old degradation could only ever produce the sole-element case;
        anything else is a real term and guessing would destroy data."""
        repair = _load_repair()
        node = {"type": "multi-pick-vocabulary", "values": ["Pf3D7", "[]"]}

        fixed, count = repair(node)

        assert fixed == node
        assert count == 0

    def test_a_string_value_of_the_same_shape_on_another_type_is_left_alone(
        self,
    ) -> None:
        repair = _load_repair()
        node = {"type": "string", "value": "[]"}

        fixed, count = repair(node)

        assert fixed == node
        assert count == 0

    def test_it_reaches_values_nested_deep_in_a_step_tree(self) -> None:
        repair = _load_repair()
        ast = {
            "recordType": "transcript",
            "root": {
                "id": "c",
                "searchName": "__combine__",
                "primaryInput": {
                    "id": "a",
                    "searchName": "GenesByOrthologPattern",
                    "parameters": {
                        "phyletic_indent_map": {
                            "type": "multi-pick-vocabulary",
                            "values": ["[]"],
                        }
                    },
                },
            },
        }

        fixed, count = repair(ast)

        assert count == 1
        params = fixed["root"]["primaryInput"]["parameters"]
        assert params["phyletic_indent_map"]["values"] == []

    def test_it_counts_every_occurrence(self) -> None:
        repair = _load_repair()
        ast = {
            "a": {"type": "multi-pick-vocabulary", "values": ["[]"]},
            "b": {"type": "multi-pick-vocabulary", "values": ["[]"]},
        }

        _fixed, count = repair(ast)

        assert count == 2

    def test_a_document_with_nothing_to_fix_reports_zero(self) -> None:
        repair = _load_repair()
        ast = {"root": {"id": "a", "parameters": {}}}

        fixed, count = repair(ast)

        assert fixed == ast
        assert count == 0

    def test_lists_of_nodes_are_walked(self) -> None:
        repair = _load_repair()
        ast = {"detachedRoots": [{"type": "multi-pick-vocabulary", "values": ["[]"]}]}

        fixed, count = repair(ast)

        assert count == 1
        assert fixed["detachedRoots"][0]["values"] == []
