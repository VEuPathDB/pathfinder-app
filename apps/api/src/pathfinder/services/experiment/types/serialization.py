"""JSON serialization for experiment types."""

from typing import cast

from assistant_core.platform.types import JSONObject

from pathfinder.services.experiment.types.experiment import Experiment


def experiment_to_json(exp: Experiment) -> JSONObject:
    """Serialize a full :class:`Experiment` to a camelCase JSON dict."""
    return cast("JSONObject", exp.model_dump(by_alias=True))
