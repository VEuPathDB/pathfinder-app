"""The six-state job machine, and the read that follows completion."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda.client import EdaClient
from veupathdb.eda.errors import EdaComputeNotReadyError, EdaError
from veupathdb.eda.models import (
    EdaComparator,
    EdaDifferentialExpressionConfig,
    EdaLabeledRange,
    EdaVariableSpec,
)
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

from pathfinder.services.eda import compute

FIXTURES = FIXTURE_DIR

pytestmark = pytest.mark.asyncio

_STUDY = "STUDY_e973eadd57"
_COMPUTE = "differentialexpression"
_LIVE_POLL_SECONDS = 120.0


def _config() -> EdaDifferentialExpressionConfig:
    return EdaDifferentialExpressionConfig(
        identifier_variable=EdaVariableSpec(
            entity_id="ENT_fd574cd6", variable_id="VEUPATHDB_GENE_ID"
        ),
        value_variable=EdaVariableSpec(
            entity_id="ENT_fd574cd6", variable_id="SEQUENCE_READ_COUNT_SENSE"
        ),
        comparator=EdaComparator(
            variable=EdaVariableSpec(
                entity_id="ENT_8151325d", variable_id="VAR_081ab087"
            ),
            group_a=[EdaLabeledRange(label="normal")],
            group_b=[EdaLabeledRange(label="febrile")],
        ),
    )


@pytest.fixture
def token() -> Iterator[None]:
    handle = veupathdb_auth_token_ctx.set("t")
    yield
    veupathdb_auth_token_ctx.reset(handle)


def _fixture_stats() -> Any:
    return json.loads((FIXTURES / "volcano_statistics.json").read_text())


async def test_a_lookup_never_starts_a_job(
    monkeypatch: pytest.MonkeyPatch, token: None
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"jobID": "a" * 32, "status": "no-such-job"})

    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=httpx.MockTransport(handler)
    )
    monkeypatch.setattr(compute, "get_eda_client", lambda _s: client)

    job = await compute.lookup_job(
        "plasmodb",
        compute_name=_COMPUTE,
        study_id=_STUDY,
        config=_config(),
        filters=[],
    )
    await client.close()
    assert job.status == "no-such-job"
    assert seen[0].url.params["autostart"] == "false"


async def test_a_submit_starts_a_job(
    monkeypatch: pytest.MonkeyPatch, token: None
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"jobID": "a" * 32, "status": "queued"})

    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=httpx.MockTransport(handler)
    )
    monkeypatch.setattr(compute, "get_eda_client", lambda _s: client)

    job = await compute.submit_compute(
        "plasmodb",
        compute_name=_COMPUTE,
        study_id=_STUDY,
        config=_config(),
        filters=[],
    )
    await client.close()
    assert job.status == "queued"
    assert seen[0].url.params["autostart"] == "true"


async def test_poll_job_reads_the_status_by_job_id(
    monkeypatch: pytest.MonkeyPatch, token: None
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"jobID": "a" * 32, "status": "in-progress", "queuePosition": 3}
        )

    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=httpx.MockTransport(handler)
    )
    monkeypatch.setattr(compute, "get_eda_client", lambda _s: client)

    job = await compute.poll_job("plasmodb", job_id="a" * 32)
    await client.close()
    assert job.status == "in-progress"
    assert job.queue_position == 3
    assert seen[0].url.path == f"/eda/jobs/{'a' * 32}"
    assert seen[0].method == "GET"


async def test_the_lookup_and_the_submit_address_the_same_job_id(
    monkeypatch: pytest.MonkeyPatch, token: None
) -> None:
    """The job id is an MD5 of the plugin name plus the key-sorted body."""
    bodies: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content.decode())
        return httpx.Response(200, json={"jobID": "a" * 32, "status": "complete"})

    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=httpx.MockTransport(handler)
    )
    monkeypatch.setattr(compute, "get_eda_client", lambda _s: client)

    await compute.lookup_job(
        "plasmodb",
        compute_name=_COMPUTE,
        study_id=_STUDY,
        config=_config(),
        filters=[],
    )
    await compute.submit_compute(
        "plasmodb",
        compute_name=_COMPUTE,
        study_id=_STUDY,
        config=_config(),
        filters=[],
    )
    await compute.read_statistics(
        "plasmodb",
        compute_name=_COMPUTE,
        study_id=_STUDY,
        config=_config(),
        filters=[],
    )
    await client.close()
    assert len(set(bodies)) == 1


async def test_the_status_sets_are_exhaustive_over_the_six_states() -> None:
    every_state = {
        "queued",
        "in-progress",
        "complete",
        "failed",
        "expired",
        "no-such-job",
    }
    settled = compute.TERMINAL_STATUSES | compute.RUNNING_STATUSES
    assert settled == every_state
    assert not (compute.TERMINAL_STATUSES & compute.RUNNING_STATUSES)


async def test_read_statistics_retries_a_502_right_after_completion(
    monkeypatch: pytest.MonkeyPatch, token: None
) -> None:
    """A read failure immediately after completion is retryable, not a failed job."""
    attempts: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(502, text="<html>Bad Gateway</html>")
        return httpx.Response(200, json=_fixture_stats())

    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=httpx.MockTransport(handler)
    )
    monkeypatch.setattr(compute, "get_eda_client", lambda _s: client)
    monkeypatch.setattr(compute, "_READ_BACKOFF_SECONDS", 0.0)

    stats = await compute.read_statistics(
        "plasmodb",
        compute_name=_COMPUTE,
        study_id=_STUDY,
        config=_config(),
        filters=[],
    )
    await client.close()
    assert len(attempts) == 2
    assert stats.statistics


async def test_read_statistics_gives_up_after_the_last_attempt(
    monkeypatch: pytest.MonkeyPatch, token: None
) -> None:
    attempts: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(502, text="<html>Bad Gateway</html>")

    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=httpx.MockTransport(handler)
    )
    monkeypatch.setattr(compute, "get_eda_client", lambda _s: client)
    monkeypatch.setattr(compute, "_READ_BACKOFF_SECONDS", 0.0)

    with pytest.raises(EdaError):
        await compute.read_statistics(
            "plasmodb",
            compute_name=_COMPUTE,
            study_id=_STUDY,
            config=_config(),
            filters=[],
        )
    await client.close()
    assert len(attempts) == 3


async def test_a_not_ready_compute_is_raised_at_once_and_never_retried(
    monkeypatch: pytest.MonkeyPatch, token: None
) -> None:
    """A 400 says the job is not done, and repeating the read cannot change that."""
    attempts: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(
            400,
            json={
                "status": "bad-request",
                "message": "Compute results are not available",
            },
        )

    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=httpx.MockTransport(handler)
    )
    monkeypatch.setattr(compute, "get_eda_client", lambda _s: client)
    monkeypatch.setattr(compute, "_READ_BACKOFF_SECONDS", 0.0)

    with pytest.raises(EdaComputeNotReadyError):
        await compute.read_statistics(
            "plasmodb",
            compute_name=_COMPUTE,
            study_id=_STUDY,
            config=_config(),
            filters=[],
        )
    await client.close()
    assert len(attempts) == 1


@pytest.mark.live_wdk
async def test_the_live_thresholds_reproduce_the_measured_counts(
    require_wdk_creds: str,
) -> None:
    """1543 genes pass at effectSize 1 and significance 0.05: 529 up, 1014 down."""
    handle = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        job = await compute.submit_compute(
            "plasmodb",
            compute_name=_COMPUTE,
            study_id=_STUDY,
            config=_config(),
            filters=[],
        )
        deadline = time.monotonic() + _LIVE_POLL_SECONDS
        while job.status in compute.RUNNING_STATUSES:
            if time.monotonic() > deadline:
                pytest.fail(f"The job did not settle; its last status is {job.status}.")
            await asyncio.sleep(2)
            job = await compute.poll_job("plasmodb", job_id=job.job_id)
        assert job.status == "complete"
        stats = await compute.read_statistics(
            "plasmodb",
            compute_name=_COMPUTE,
            study_id=_STUDY,
            config=_config(),
            filters=[],
        )
    finally:
        veupathdb_auth_token_ctx.reset(handle)
    summary = compute.retained_summary(
        stats, effect_size_threshold=1.0, significance_threshold=0.05
    )
    assert summary.total_rows == 5511
    assert summary.unparseable_rows == 1
    assert summary.retained == 1543
    assert summary.retained_up == 529
    assert summary.retained_down == 1014
