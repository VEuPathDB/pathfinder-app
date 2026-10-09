from __future__ import annotations

import logging

import procrastinate
import pytest
from procrastinate.testing import InMemoryConnector

from pathfinder.jobs.logging_filters import install_procrastinate_redaction

_SENTINEL = "find kinases upregulated in the liver stage 7f3a"
_TOKEN = "secret-cookie-value-12345"


async def _run_one_job(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    app = procrastinate.App(connector=InMemoryConnector())

    @app.task(queue="probe", name="probe")
    async def probe(payload: dict[str, str]) -> str:
        return payload["text"]

    install_procrastinate_redaction()
    with caplog.at_level(logging.DEBUG, logger="procrastinate"):
        async with app.open_async():
            await probe.defer_async(
                payload={"text": _SENTINEL, "veupathdb_auth_token": _TOKEN}
            )
            await app.run_worker_async(
                queues=["probe"],
                wait=False,
                listen_notify=False,
                install_signal_handlers=False,
            )
    return [r for r in caplog.records if r.name.startswith("procrastinate")]


def _everything_logged(record: logging.LogRecord) -> str:
    return logging.Formatter().format(record) + repr(record.__dict__)


async def test_no_procrastinate_record_carries_the_task_arguments(
    caplog: pytest.LogCaptureFixture,
) -> None:
    records = await _run_one_job(caplog)

    logged = [_everything_logged(record) for record in records]
    assert [text for text in logged if _SENTINEL in text or _TOKEN in text] == []
    assert any("Starting job probe[1]" in r.getMessage() for r in records)


async def test_a_job_record_keeps_its_name_id_queue_and_status(
    caplog: pytest.LogCaptureFixture,
) -> None:
    records = await _run_one_job(caplog)

    (ended,) = [r for r in records if "ended with status" in r.getMessage()]
    assert ended.__dict__["job"] == {
        "id": 1,
        "task_name": "probe",
        "queue": "probe",
        "status": "doing",
    }
    assert ended.getMessage().startswith("Job probe[1] ended with status: Success")


async def test_the_deferral_record_lists_the_jobs_without_their_arguments(
    caplog: pytest.LogCaptureFixture,
) -> None:
    records = await _run_one_job(caplog)

    (deferred,) = [r for r in records if r.getMessage() == "Deferred 1 job"]
    assert deferred.__dict__["jobs"] == [
        {"id": 1, "task_name": "probe", "queue": "probe", "status": "todo"}
    ]


def test_a_record_of_another_library_is_left_alone(
    caplog: pytest.LogCaptureFixture,
) -> None:
    install_procrastinate_redaction()
    with caplog.at_level(logging.INFO, logger="httpx"):
        logging.getLogger("httpx").info("GET %s", _SENTINEL)

    (record,) = caplog.records
    assert record.getMessage() == f"GET {_SENTINEL}"


def test_installing_twice_attaches_one_filter() -> None:
    install_procrastinate_redaction()
    install_procrastinate_redaction()

    worker_logger = logging.getLogger("procrastinate.worker")
    assert len(worker_logger.filters) == len(set(map(type, worker_logger.filters)))
