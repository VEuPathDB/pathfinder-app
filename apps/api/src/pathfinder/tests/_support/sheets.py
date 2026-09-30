"""A search's sheet as the visible text parameters it names, each shown by its
name and named once."""

from __future__ import annotations

from collections.abc import Iterable

from veupathdb_mcp.catalog import ParameterInfo


def visible_sheet(names: Iterable[str]) -> list[ParameterInfo]:
    return [
        ParameterInfo.model_validate(
            {
                "name": name,
                "display_name": name,
                "type": "string",
                "required": False,
                "is_visible": True,
                "help": "",
                "value_format": "",
            }
        )
        for name in dict.fromkeys(names)
    ]
