"""The identity a request is served under."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from pathfinder.platform.identity import PATHFINDER_APPLICATION_ID
from pathfinder.platform.principal import Principal

USER_ID = UUID("11111111-2222-3333-4444-555555555555")


def _assign(target: object, field: str, value: str) -> None:
    """Write one field of a model, whatever the model allows."""
    setattr(target, field, value)


class TestPrincipal:
    def test_the_application_defaults_to_pathfinder(self) -> None:
        principal = Principal(user_id=USER_ID, credential="pathfinder-cookie")

        assert principal.application_id == PATHFINDER_APPLICATION_ID
        assert principal.application_id == "pathfinder"

    def test_the_principal_is_immutable(self) -> None:
        principal = Principal(user_id=USER_ID, credential="pathfinder-cookie")

        with pytest.raises(ValidationError):
            _assign(principal, "application_id", "other")

    def test_an_unknown_credential_kind_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Principal.model_validate(
                {"userId": str(USER_ID), "credential": "basic-auth"}
            )

    def test_the_json_form_uses_camel_case(self) -> None:
        principal = Principal(
            user_id=USER_ID,
            application_id="analytics",
            credential="veupathdb-bearer",
        )

        assert principal.model_dump(by_alias=True, mode="json") == {
            "userId": str(USER_ID),
            "applicationId": "analytics",
            "credential": "veupathdb-bearer",
        }
