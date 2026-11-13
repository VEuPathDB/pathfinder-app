from __future__ import annotations

from pydantic import GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, PydanticOmit


class OmittedFromInput:
    """A field the validation schema omits and the serialization schema keeps."""

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        if handler.mode == "validation":
            raise PydanticOmit
        return handler(schema)
