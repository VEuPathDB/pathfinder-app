"""Service-layer response models the WDK step services produce.

Owned by the service (the producer) so a caller returns them without
importing the wire models.
"""

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from pydantic import Field, JsonValue

from pathfinder.domain.wdk_values import WDKRecordIdPart


class SampleRecordsResult(CamelModel):
    """The first records of one built step, ready to render."""

    step_id: int
    total_count: int
    records: list[JSONObject] = Field(default_factory=list)
    attributes: list[str] = Field(default_factory=list)


class RecordAttribute(CamelModel):
    name: str
    display_name: str
    help: str | None
    type: str | None
    is_displayable: bool
    is_sortable: bool
    is_suggested: bool


class AttributesResponse(CamelModel):
    attributes: list[RecordAttribute]
    record_type: str


class RecordDetailResponse(CamelModel):
    display_name: str
    id: list[WDKRecordIdPart]
    record_class_name: str
    attributes: dict[str, JsonValue]
    attribute_names: dict[str, str]
    tables: dict[str, JsonValue]
    table_errors: list[str]
