"""A search's sheet as the visible text parameters it names, and the declarations
a sheet was read from."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from pydantic import TypeAdapter
from veupathdb.wdk import WDKParameter
from veupathdb_mcp.catalog import ParameterInfo, is_phyletic_sheet


def visible_sheet(names: Iterable[str]) -> list[ParameterInfo]:
    return [
        ParameterInfo.model_validate(
            {
                "name": name,
                "display_name": name,
                "type": "string",
                "required": False,
                "is_visible": True,
                "site_set": False,
                "help": "",
            }
        )
        for name in dict.fromkeys(names)
    ]


_DECLARED: TypeAdapter[WDKParameter] = TypeAdapter(WDKParameter)
_PUBLISHED_ORGANISM_PROPERTIES = [
    "pruneNodesWithSingleExtendingChild",
    "showOnlyPreferredOrganisms",
    "highlightReferenceOrganisms",
]


def _declared(info: ParameterInfo, children: list[str]) -> WDKParameter:
    facets = info.facets().root
    return _DECLARED.validate_python(
        {
            "name": info.name,
            "type": info.param_kind,
            "displayName": info.display_name,
            "help": info.help,
            "isVisible": info.is_visible,
            "isReadOnly": info.is_read_only or (info.site_set and info.is_visible),
            "allowEmptyValue": not info.required,
            "initialDisplayValue": info.default_value,
            "isNumber": info.is_number,
            "min": info.min,
            "max": info.max,
            "dependentParams": children,
            "properties": {"organismProperties": _PUBLISHED_ORGANISM_PROPERTIES}
            if info.organism_param
            else {},
            "displayType": "select",
            "vocabulary": [[o.value, o.display, None] for o in info.vocabulary()]
            if info.param_kind.endswith("vocabulary") and info.vocabulary()
            else None,
            "ontology": [
                {
                    "term": f.term,
                    "display": f.display,
                    "parent": f.parent,
                    "type": f.type,
                    "isRange": f.is_range,
                    "units": f.units,
                    "precision": f.precision,
                }
                for f in facets
            ],
            "values": {f.term: f.members for f in facets},
        }
    )


def declarations(infos: Sequence[ParameterInfo]) -> list[WDKParameter]:
    """The declarations a hand-built sheet stands for, each parent naming its
    children. A formatted phyletic sheet has lost its map parameters, so it is
    refused."""
    if is_phyletic_sheet(list(infos)):
        msg = (
            "A formatted phyletic sheet drops its two map parameters; serve the "
            "recorded declarations with declared=."
        )
        raise ValueError(msg)
    return [
        _declared(
            info,
            [
                child.name
                for child in infos
                if info.name in {*child.wire_parents, *child.stated_parents}
            ],
        )
        for info in infos
    ]
