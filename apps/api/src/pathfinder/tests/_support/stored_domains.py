from __future__ import annotations

from pathlib import Path

import ormsgpack
from langgraph.checkpoint.serde.jsonplus import EXT_PYDANTIC_V2
from pydantic import TypeAdapter

from pathfinder.ai.graph.state import StrategyDomainState

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "checkpoints"


_STORED = TypeAdapter(dict[str, object])


def stored_domain(name: str) -> dict[str, object]:
    return _STORED.validate_json((_FIXTURES / f"{name}.json").read_text())


def stored_domain_blob(name: str) -> tuple[str, bytes]:
    payload = (
        StrategyDomainState.__module__,
        StrategyDomainState.__name__,
        stored_domain(name),
        "model_validate_json",
    )
    return "msgpack", ormsgpack.packb(
        ormsgpack.Ext(EXT_PYDANTIC_V2, ormsgpack.packb(payload))
    )
