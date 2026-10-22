"""Audit read endpoints. The work lives in ``services.audit``."""

from fastapi import APIRouter

from . import findings, runs

_PREFIX = "/api/v1/audits"

router = APIRouter(tags=["audits"])

for _sub in (runs.router, findings.router):
    router.include_router(_sub, prefix=_PREFIX)
