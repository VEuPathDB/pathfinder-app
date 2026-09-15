"""Build ExperimentConfig from HTTP request DTOs.

This is a transport-layer adapter: it converts the HTTP-specific
``CreateExperimentRequest`` Pydantic model into the service-layer
``ExperimentConfig`` model. Lives here (not in services/) because
it depends on transport schemas.
"""

from uuid import UUID

from pathfinder.services.experiment.types import ExperimentConfig
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.store import get_gene_set_store
from pathfinder.transport.http.schemas.experiments import CreateExperimentRequest


async def config_from_request(
    req: CreateExperimentRequest,
    user_id: UUID,
) -> ExperimentConfig:
    """Build :class:`ExperimentConfig` from a create request DTO.

    Both models share identical Python field names, so ``model_validate``
    handles the bulk conversion. Only ``parameter_display_values`` needs
    explicit handling: its keys and values are stringified. A config that
    names a gene set names one ``user_id`` holds.

    :raises NotFoundError: If the gene set is missing or held by anyone else.
    """
    data = req.model_dump()

    pdv = data.get("parameter_display_values")
    if isinstance(pdv, dict):
        data["parameter_display_values"] = {str(k): str(v) for k, v in pdv.items()}

    config = ExperimentConfig.model_validate(data)
    if config.gene_set_id is not None:
        await GeneSetService(get_gene_set_store()).get_for_user(
            user_id,
            config.gene_set_id,
        )
    return config
