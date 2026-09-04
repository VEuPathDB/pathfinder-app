"""Threshold-sweep endpoint for experiments."""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from pathfinder.services.experiment.sweep_service import (
    compute_sweep_values,
    generate_sweep_events,
    validate_sweep_parameter,
)
from pathfinder.transport.http.deps import (
    CurrentUser,
    ExperimentDep,
    require_registered_wdk_identity,
)
from pathfinder.transport.http.schemas.experiments import ThresholdSweepRequest
from pathfinder.transport.http.sse_utils import (
    SSE_RESPONSES,
    typed_event_stream_response,
)

router = APIRouter()


@router.post(
    "/{experiment_id}/threshold-sweep",
    responses=SSE_RESPONSES,
    dependencies=[Depends(require_registered_wdk_identity)],
)
async def threshold_sweep(
    exp: ExperimentDep,
    request: ThresholdSweepRequest,
    user_id: CurrentUser,
) -> StreamingResponse:
    """Sweep a parameter across a range and stream metrics as they complete."""
    validate_sweep_parameter(exp, request.parameter_name)
    sweep_values = compute_sweep_values(
        sweep_type=request.sweep_type,
        values=request.values,
        lo=request.min,
        hi=request.max,
        steps=request.steps,
    )

    events = generate_sweep_events(
        exp=exp,
        param_name=request.parameter_name,
        sweep_type=request.sweep_type,
        sweep_values=sweep_values,
    )
    return typed_event_stream_response(
        events,
        event_name=lambda e: e.type,
    )
