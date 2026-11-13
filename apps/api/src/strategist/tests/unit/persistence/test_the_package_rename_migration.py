import base64
import importlib.util
import json
import pathlib
from typing import Any

import ormsgpack
import pytest
from assistant_core.conversation.serde import build_checkpoint_serde
from langgraph.checkpoint.serde.jsonplus import EXT_DELTA_SNAPSHOT, EXT_PYDANTIC_V2
from pydantic_ai.ui.vercel_ai.request_types import TextUIPart

from strategist.ai.graph.state import PipelineState, StrategyDomainState
from strategist.assistants.strategist_spec import STRATEGIST_CHECKPOINT_TYPES
from strategist.domain.strategy.constraints import ConstraintKind
from strategist.tests._support.checkpoint_state import populated_state, search_overview

_ROOT = pathlib.Path(__file__).resolve().parents[5]
_MIGRATION = (
    _ROOT
    / "alembic"
    / "versions"
    / "2026_11_13_0001_the_package_is_named_strategist.py"
)
_RECORDED = (
    _ROOT
    / "src"
    / "strategist"
    / "tests"
    / "fixtures"
    / "checkpoints"
    / "channels-under-the-pathfinder-package.json"
)
_SERDE = build_checkpoint_serde(STRATEGIST_CHECKPOINT_TYPES)
_OPTION = ormsgpack.OPT_NON_STR_KEYS


def _migration() -> Any:
    spec = importlib.util.spec_from_file_location("_package_migration", _MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _recorded() -> dict[str, bytes]:
    stored: dict[str, str] = json.loads(_RECORDED.read_text())
    return {channel: base64.b64decode(blob) for channel, blob in stored.items()}


def _upgraded(blob: bytes) -> bytes:
    renamed: bytes = _migration().renamed_package(blob, "pathfinder", "strategist")
    return renamed


def _downgraded(blob: bytes) -> bytes:
    renamed: bytes = _migration().renamed_package(blob, "strategist", "pathfinder")
    return renamed


def _type_reference(module: str) -> ormsgpack.Ext:
    return ormsgpack.Ext(
        EXT_PYDANTIC_V2,
        ormsgpack.packb((module, "VerificationDigest", {}, "model_validate_json")),
    )


def test_the_recorded_domain_is_unreadable_under_the_new_package() -> None:
    stored = _SERDE.loads_typed(("msgpack", _recorded()["domain"]))

    assert type(stored) is dict


@pytest.mark.parametrize("channel", sorted(_recorded()))
def test_every_recorded_channel_reads_back_as_the_state_it_held(channel: str) -> None:
    stored = _SERDE.loads_typed(("msgpack", _upgraded(_recorded()[channel])))

    assert stored == getattr(populated_state(), channel)


@pytest.mark.parametrize("channel", sorted(_recorded()))
def test_every_recorded_channel_becomes_the_bytes_the_new_package_writes(
    channel: str,
) -> None:
    _, written = _SERDE.dumps_typed(getattr(populated_state(), channel))

    assert _upgraded(_recorded()[channel]) == written


def test_the_recorded_domain_reads_back_as_its_types() -> None:
    domain = _SERDE.loads_typed(("msgpack", _upgraded(_recorded()["domain"])))

    assert type(domain) is StrategyDomainState
    assert (
        PipelineState.model_validate(
            {
                channel: _SERDE.loads_typed(("msgpack", _upgraded(blob)))
                for channel, blob in _recorded().items()
            }
        )
        == populated_state()
    )


def test_the_upgrade_names_each_type_under_the_new_package() -> None:
    old = _recorded()["domain"]
    new = _upgraded(old)

    assert old.count(b"pathfinder.") == 7
    assert new.count(b"strategist.") == 7
    assert b"pathfinder" not in new


@pytest.mark.parametrize("channel", sorted(_recorded()))
def test_the_downgrade_restores_every_recorded_byte(channel: str) -> None:
    old = _recorded()[channel]

    assert _downgraded(_upgraded(old)) == old


def test_a_blob_that_names_no_module_of_the_package_is_unchanged() -> None:
    _, blob = _SERDE.dumps_typed(
        {"note": "pathfinder.qa holds the site", "parts": [TextUIPart(text="hi")]}
    )

    assert b"pathfinder." in blob
    assert _upgraded(blob) == blob


def test_a_type_nested_in_lists_and_maps_is_renamed_in_place() -> None:
    value = {
        "kinds": [ConstraintKind.ORGANISM],
        "found": {"GenesByTaxon": [search_overview("gene")]},
    }
    _, current = _SERDE.dumps_typed(value)

    old = _downgraded(current)

    assert b"pathfinder.domain.strategy.constraints" in old
    assert b"strategist" not in old
    assert _upgraded(old) == current
    assert _SERDE.loads_typed(("msgpack", _upgraded(old))) == value


def test_an_extension_the_serializer_does_not_name_keeps_its_bytes() -> None:
    unknown = ormsgpack.Ext(42, b"\x01pathfinder.ai")
    blob = ormsgpack.packb(
        [unknown, _type_reference("pathfinder.ai.graph.state")], option=_OPTION
    )

    assert _upgraded(blob) == ormsgpack.packb(
        [unknown, _type_reference("strategist.ai.graph.state")], option=_OPTION
    )


def test_a_delta_snapshot_renames_the_types_it_wraps() -> None:
    old = _recorded()["domain"]
    blob = ormsgpack.packb(ormsgpack.Ext(EXT_DELTA_SNAPSHOT, old))

    assert _upgraded(blob) == ormsgpack.packb(
        ormsgpack.Ext(EXT_DELTA_SNAPSHOT, _upgraded(old))
    )


def test_a_module_that_only_starts_with_the_old_name_is_unchanged() -> None:
    blob = ormsgpack.packb(_type_reference("pathfinderish.ai"))

    assert _upgraded(blob) == blob
