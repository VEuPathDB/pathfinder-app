"""Whether a site error is a refusal or a site that did not answer, and which site it was."""

from __future__ import annotations

import httpx
from veupathdb.errors import VEuPathDBError, VEuPathDBErrorCode
from veupathdb.jbrowse import JBrowseError
from veupathdb.wdk import SiteInfo, list_sites

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


def answered_with_a_status(exc: BaseException | None) -> bool:
    match exc:
        case httpx.HTTPStatusError():
            return True
        case VEuPathDBError():
            return answered_with_a_status(exc.__cause__)
        case _:
            return False


def unreached(exc: BaseException | None) -> bool:
    match exc:
        case httpx.TransportError() | TimeoutError() | ConnectionError():
            return True
        case VEuPathDBError(code=VEuPathDBErrorCode.DATA_PARSING_ERROR):
            return False
        case _:
            status = site_status(exc)
            return status is not None and status >= _SERVER_ERROR


class SiteDidNotAnswerError(Exception):
    def __init__(self, site: SiteInfo, *, changed_nothing: bool) -> None:
        self.site = site
        self.changed_nothing = changed_nothing
        super().__init__(f"{site.name} did not answer.")


def _requested_url(exc: BaseException | None) -> httpx.URL | None:
    match exc:
        case None:
            return None
        case httpx.HTTPStatusError():
            return exc.request.url
        case httpx.RequestError():
            try:
                return exc.request.url
            except RuntimeError:
                return None
        case _:
            return _requested_url(exc.__cause__)


def unanswered_site(exc: BaseException) -> SiteInfo | None:
    url = _requested_url(exc) if unreached(exc) else None
    if url is None:
        return None
    origin = f"{url.scheme}://{url.netloc.decode()}"
    return next((site for site in list_sites() if site.site_origin == origin), None)
