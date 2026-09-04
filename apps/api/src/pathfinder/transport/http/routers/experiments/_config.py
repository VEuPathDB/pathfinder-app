"""Build ExperimentConfig from HTTP request DTOs.

This is a transport-layer adapter: it converts the HTTP-specific
``CreateExperimentRequest`` Pydantic model into the service-layer
``ExperimentConfig`` model. Lives here (not in services/) because
it depends on transport schemas.
"""

from pathfinder.services.experiment.types import ExperimentConfig
from pathfinder.transport.http.schemas.experiments import CreateExperimentRequest


def config_from_request(req: CreateExperimentRequest) -> ExperimentConfig:
    """Build :class:`ExperimentConfig` from a create request DTO.

    Both models share identical Python field names, so ``model_validate``
    handles the bulk conversion. Only ``parameter_display_values`` needs
    explicit handling: its keys and values are stringified.
    """
    data = req.model_dump()

    pdv = data.get("parameter_display_values")
    if isinstance(pdv, dict):
        data["parameter_display_values"] = {str(k): str(v) for k, v in pdv.items()}

    return ExperimentConfig.model_validate(data)
