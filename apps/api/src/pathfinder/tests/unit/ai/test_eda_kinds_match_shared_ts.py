"""The registered kinds and the TypeScript union say the same thing."""

from __future__ import annotations

import re
from pathlib import Path

from assistant_core.conversation.stream_parts.registry import StreamPartRegistry

from pathfinder.ai.eda_stream_parts import register_eda_stream_parts


def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "package.json").is_file() and (candidate / "packages").is_dir():
            return candidate
    msg = "no repository root above this test"
    raise AssertionError(msg)


TYPES_TS = _repository_root() / "packages" / "shared-ts" / "src" / "types.ts"

_KIND = re.compile(r'"(data-eda\.[a-z-]+)"')


def _declared_kinds() -> set[str]:
    return set(_KIND.findall(TYPES_TS.read_text()))


def _registered_kinds() -> frozenset[str]:
    registry = StreamPartRegistry()
    register_eda_stream_parts(registry)
    return registry.kinds()


def test_the_types_file_is_the_one_the_frontend_compiles() -> None:
    assert TYPES_TS.is_file()
    assert "KnownDataPartKind" in TYPES_TS.read_text()


def test_every_registered_eda_kind_appears_in_the_typescript_union() -> None:
    assert _registered_kinds() <= _declared_kinds()


def test_the_typescript_union_declares_no_eda_kind_the_backend_does_not_emit() -> None:
    assert _declared_kinds() <= _registered_kinds()


def test_the_three_pinned_kinds_are_registered() -> None:
    assert _registered_kinds() == {
        "data-eda.analysis-state",
        "data-eda.subset-preview",
        "data-eda.viz",
    }


def test_every_eda_kind_has_an_entry_in_the_payload_map() -> None:
    text = TYPES_TS.read_text()
    start = text.index("interface DataPartPayloadMap")
    end = text.index("}", start)
    body = text[start:end]
    for kind in _declared_kinds():
        assert f'"{kind}"' in body, kind
