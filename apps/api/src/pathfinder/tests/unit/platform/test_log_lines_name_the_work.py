from __future__ import annotations

import logging
from uuid import UUID, uuid4

import pytest
from assistant_core.platform.logging import get_logger
from pydantic import ValidationError

from pathfinder.platform.log_ids import LogIds, accepted_request_id, log_ids_scope
from pathfinder.tests._support.rendered_logs import rendered_logs

_NAMED = {"conversation_id", "user_id", "turn_id", "site_id"}


def test_a_library_line_inside_a_scope_names_the_work_and_none_after_it() -> None:
    ids = LogIds(
        conversation_id=uuid4(),
        user_id=uuid4(),
        turn_id=uuid4(),
        site_id="plasmodb",
    )

    with rendered_logs() as logs:
        with log_ids_scope(ids):
            logging.getLogger("procrastinate.worker.worker").warning("library inside")
            get_logger("pathfinder.probe").warning("own inside")
        logging.getLogger("procrastinate.worker.worker").warning("library after")

    expected = ids.named()
    for event in ("library inside", "own inside"):
        line = logs.line(event)
        assert {key: line[key] for key in expected} == expected
    assert _NAMED & set(logs.line("library after")) == set()


def test_an_absent_id_is_not_named() -> None:
    ids = LogIds(run_id=uuid4())

    with rendered_logs() as logs, log_ids_scope(ids):
        logging.getLogger("httpx").warning("one id")

    line = logs.line("one id")
    assert line["run_id"] == str(ids.run_id)
    assert _NAMED & set(line) == set()


@pytest.mark.parametrize(
    "field",
    [
        {"site_id": "a@b.org"},
        {"site_id": "plasmo db"},
        {"assistant_id": "Ahmed Muharram"},
        {"method": "BREW"},
        {"route": "/api/v1/x?email=a@b.org"},
        {"route": "free text"},
        {"route": "/api/v1/conversations/{strategyId:uuid}"},
    ],
)
def test_a_value_that_is_not_an_id_is_refused(field: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        LogIds.model_validate(field)


def test_an_empty_site_is_no_site() -> None:
    assert LogIds(site_id="").named() == {}


@pytest.mark.parametrize("header", ["request-one", str(uuid4())])
def test_a_request_id_that_is_an_id_is_kept(header: str) -> None:
    assert accepted_request_id(header) == header


@pytest.mark.parametrize("header", [None, "", "a@b.org", "free text", "x" * 65])
def test_a_request_id_that_is_not_an_id_is_replaced(header: str | None) -> None:
    minted = accepted_request_id(header)
    assert minted != header
    assert UUID(minted).version == 4
