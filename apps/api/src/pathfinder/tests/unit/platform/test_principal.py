"""The identity a request is served under."""

import pytest
from assistant_core.platform.context import DEFAULT_APPLICATION_ID
from pydantic import ValidationError

from pathfinder.platform.principal import Principal

USER_ID = "11111111-2222-3333-4444-555555555555"


class TestPrincipal:
    def test_the_application_defaults_to_pathfinder(self) -> None:
        principal = Principal(user_id=USER_ID, credential="pathfinder-cookie")

        assert principal.application_id == DEFAULT_APPLICATION_ID
        assert principal.application_id == "pathfinder"

    def test_the_principal_is_immutable(self) -> None:
        principal = Principal(user_id=USER_ID, credential="pathfinder-cookie")

        with pytest.raises(ValidationError):
            principal.application_id = "other"

    def test_an_unknown_credential_kind_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Principal(user_id=USER_ID, credential="basic-auth")

    def test_the_json_form_uses_camel_case(self) -> None:
        principal = Principal(
            user_id=USER_ID,
            application_id="analytics",
            credential="veupathdb-bearer",
        )

        assert principal.model_dump(by_alias=True, mode="json") == {
            "userId": USER_ID,
            "applicationId": "analytics",
            "credential": "veupathdb-bearer",
        }
