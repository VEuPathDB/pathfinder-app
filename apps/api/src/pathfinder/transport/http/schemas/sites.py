"""Sites request/response DTOs."""

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONArray, JSONObject
from pydantic import ConfigDict, Field
from veupathdb.domain.parameters.values import ParamValue


class SiteResponse(CamelModel):
    """VEuPathDB site information."""

    id: str
    name: str
    display_name: str
    base_url: str
    project_id: str
    is_portal: bool


class RecordTypeResponse(CamelModel):
    """Record type information."""

    name: str
    display_name: str
    description: str | None = None


class SearchResponse(CamelModel):
    """Search information."""

    name: str
    display_name: str
    description: str | None = None
    record_type: str


class DependentParamsRequest(CamelModel):
    """Dependent parameter values request."""

    parameter_name: str
    context_values: dict[str, ParamValue] = Field(default_factory=dict)


class SearchDetailsResponse(CamelModel):
    """Search details payload (UI-facing)."""

    search_data: JSONObject | None = Field(default=None)
    validation: JSONObject | None = None
    search_config: JSONObject | None = Field(default=None)
    parameters: JSONArray | None = None
    param_map: JSONObject | None = Field(default=None)
    question: JSONObject | None = None

    model_config = ConfigDict(extra="allow")


class SearchValidationRequest(CamelModel):
    """Search parameter validation request."""

    context_values: dict[str, ParamValue] = Field(default_factory=dict)


class ParamSpecsRequest(CamelModel):
    """Parameter specs request (optionally contextual)."""

    context_values: dict[str, ParamValue] = Field(default_factory=dict)
