"""Whether a site error is a refusal or a site that did not answer, judged by its status."""

from __future__ import annotations

import httpx
from veupathdb.errors import VEuPathDBError, VEuPathDBErrorCode
from veupathdb.jbrowse import JBrowseError

_SERVER_ERROR = 500


def site_status(exc: BaseException | None) -> int | None:
    match exc:
        case httpx.HTTPStatusError():
            return exc.response.status_code
        case JBrowseError():
            return exc.upstream_status
        case VEuPathDBError():
            return exc.status
        case _:
            return None


def unreached(exc: BaseException | None) -> bool:
    match exc:
        case httpx.TransportError() | TimeoutError() | ConnectionError():
            return True
        case VEuPathDBError(code=VEuPathDBErrorCode.DATA_PARSING_ERROR):
            return False
        case _:
            status = site_status(exc)
            return status is not None and status >= _SERVER_ERROR
