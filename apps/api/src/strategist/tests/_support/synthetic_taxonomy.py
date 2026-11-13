"""A small invented clade tree with codes no real taxonomy uses."""

from __future__ import annotations

from pydantic import TypeAdapter
from veupathdb.domain.parameters import PhyleticNode, PhyleticTree
from veupathdb_mcp.catalog import PhyleticPattern

PATTERN: TypeAdapter[PhyleticPattern] = TypeAdapter(PhyleticPattern)

FERNS = ("fna", "fnb", "fnc")
MOSSES = ("msa", "msb")
LONE = "lna"


def _genome(code: str, label: str) -> PhyleticNode:
    return PhyleticNode(code=code, label=label, depth=2, clade=False)


def synthetic_tree() -> PhyleticTree:
    ferns = PhyleticNode(
        code="FERN",
        label="Ferns",
        depth=1,
        clade=True,
        children=[
            _genome("fna", "Fernia alba one"),
            _genome("fnb", "Fernia alba two"),
            _genome("fnc", "Fernia nigra one"),
        ],
    )
    mosses = PhyleticNode(
        code="MOSS",
        label="Mosses",
        depth=1,
        clade=True,
        children=[
            _genome("msa", "Mossia rubra one"),
            _genome("msb", "Mossia viridis one"),
        ],
    )
    return PhyleticTree(
        roots=[
            PhyleticNode(
                code="PLNT",
                label="Plants",
                depth=0,
                clade=True,
                children=[ferns, mosses, _genome(LONE, "Lonia sola one")],
            )
        ]
    )


def pattern(raw: object) -> PhyleticPattern:
    return PATTERN.validate_python(raw)
