from typing import Any
from urllib.parse import urlsplit

import pytest
import yaml

from strategist.platform.paths import REPO_ROOT

_E2E = "docker-compose.e2e.yml"
_RECORD = "docker-compose.e2e-wire-record.yml"
_WIRE = "http://wdk-wire:8080"


def _services(relative: str) -> dict[str, Any]:
    text = (REPO_ROOT / relative).read_text()
    plain = text.replace(" !override", "").replace(" !reset", "")
    services: dict[str, Any] = yaml.safe_load(plain)["services"]
    return services


def _test_site_hosts() -> set[str]:
    sites = yaml.safe_load((REPO_ROOT / "e2e-sites.yaml").read_text())["sites"]
    return {urlsplit(site["base_url"]).hostname for site in sites.values()}


@pytest.mark.parametrize("name", ["api", "worker"])
def test_the_e2e_overlay_sends_every_veupathdb_call_through_wdk_wire(name: str) -> None:
    service = _services(_E2E)[name]

    assert (
        service["environment"]["HTTPS_PROXY"],
        service["environment"]["https_proxy"],
        service["environment"]["VEUPATHDB_OAUTH_URL"],
        service["depends_on"]["wdk-wire"]["condition"],
    ) == (_WIRE, _WIRE, "https://auth.wire.test", "service_healthy")


@pytest.mark.parametrize("name", ["api", "worker", "wdk-wire"])
def test_the_e2e_overlay_fences_every_test_site(name: str) -> None:
    fenced = {
        entry.removesuffix(":127.0.0.1")
        for entry in _services(_E2E)[name]["extra_hosts"]
    }

    assert _test_site_hosts() | {"api.openai.com"} <= fenced


def test_the_e2e_overlay_runs_wdk_wire_in_replay_on_read_only_recordings() -> None:
    wire = _services(_E2E)["wdk-wire"]

    assert wire["environment"]["WIRE_MODE"] == "replay"
    assert "${WIRE_DIR:-./apps/web/e2e/wire}:/wire/recordings:ro" in wire["volumes"]


def test_the_record_overlay_writes_only_where_its_caller_names() -> None:
    wire = _services(_RECORD)["wdk-wire"]

    assert wire["environment"]["WIRE_MODE"] == "record"
    assert wire["volumes"] == [
        "${WIRE_DIR:?the record overlay runs only through scripts/e2e-wire.sh}:/wire/recordings:rw"
    ]


def test_the_record_overlay_reaches_qa_through_the_callers_upstream() -> None:
    wire = _services(_RECORD)["wdk-wire"]

    assert (
        wire["environment"]["WIRE_UPSTREAM"],
        wire["environment"]["HTTPS_PROXY"],
    ) == ("${WIRE_UPSTREAM:-}", "${WIRE_UPSTREAM:-}")


def test_a_replaying_wdk_wire_names_no_upstream() -> None:
    wire = _services(_E2E)["wdk-wire"]

    assert {"WIRE_UPSTREAM", "HTTPS_PROXY"}.isdisjoint(wire["environment"])
