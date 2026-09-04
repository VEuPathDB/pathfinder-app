"""Experiment Lab endpoints, split into sub-routers by responsibility."""

from fastapi import APIRouter

from . import enrichment, evaluation, execution, results

_PREFIX = "/api/v1/experiments"

router = APIRouter(tags=["experiments"])

# The literal paths (/batch, /benchmark, /seed) register before /{experiment_id}.
for _sub in (execution.router, enrichment.router, evaluation.router, results.router):
    router.include_router(_sub, prefix=_PREFIX)
