"""What a WDK refusal is, and what PathFinder keeps of it.

One mapper converts the exceptions WDK raises deliberately into responses, so
for those the status code is the whole diagnosis, and every body is
``text/plain`` whatever it holds.
"""

from __future__ import annotations

import pytest

from pathfinder.ai.capabilities.error_classification import (
    ErrorCategory,
    classify_error,
)
from pathfinder.devtools.wdk_fixtures import load_recorded
from pathfinder.integrations.veupathdb._failures import validation_bundle, wdk_failure
from pathfinder.platform.errors import WDKError

_SERVER_ERROR = 500


class TestWdkHttp002FailureIsAStatusAndPlainText:
    @pytest.mark.parametrize(
        ("name", "status"),
        [
            ("search_under_the_wrong_record_type", 404),
            ("search_by_full_name", 404),
            ("refresh_without_changed_param", 400),
            ("refresh_with_a_non_string_value", 400),
            ("refresh_with_a_value_outside_the_vocabulary", 422),
            ("refresh_with_an_unknown_parameter", 422),
        ],
    )
    def test_wdk_http_002_every_error_body_is_text_plain(
        self, name: str, status: int
    ) -> None:
        recorded = load_recorded(name)

        assert recorded.provenance.status == status
        assert recorded.provenance.content_type.startswith("text/plain")

    def test_wdk_http_002_a_422_serves_json_under_text_plain(self) -> None:
        # Deciding how to read a WDK error by its content type gets it wrong.
        recorded = load_recorded("refresh_with_a_value_outside_the_vocabulary")

        assert recorded.provenance.content_type.startswith("text/plain")
        assert validation_bundle(recorded.raw_text()) is not None

    def test_wdk_http_002_a_400_is_prose_and_a_422_is_a_verdict(self) -> None:
        # 400 is our serialization; 422 is the scientist's value. Only one of
        # those is worth showing a user.
        misformat = load_recorded("refresh_without_changed_param")
        rejected = load_recorded("refresh_with_a_value_outside_the_vocabulary")

        assert validation_bundle(misformat.raw_text()) is None
        verdict = validation_bundle(rejected.raw_text())
        assert verdict is not None
        assert "is invalid" in " ".join(verdict.messages())

    @pytest.mark.parametrize("status", [400, 404, 409, 422])
    def test_wdk_http_002_nothing_below_500_is_retried(self, status: int) -> None:
        assert (
            classify_error(WDKError("refused", status=status)) is ErrorCategory.SEMANTIC
        )

    @pytest.mark.parametrize("status", [502, 503])
    def test_wdk_http_002_a_server_failure_is_transient(self, status: int) -> None:
        assert status >= _SERVER_ERROR
        assert (
            classify_error(WDKError("down", status=status)) is ErrorCategory.TRANSIENT
        )


class TestWdkValid006ARefusalCarriesItsBundle:
    def test_wdk_valid_006_the_messages_reach_the_error(self) -> None:
        recorded = load_recorded("refresh_with_a_value_outside_the_vocabulary")

        error = wdk_failure(
            "POST", "/refreshed-dependent-params", 422, recorded.raw_text()
        )

        assert "The passed changed param value 'Nope' is invalid." in str(error)

    def test_wdk_valid_006_the_level_names_which_check_rejected_you(self) -> None:
        recorded = load_recorded("refresh_with_an_unknown_parameter")

        error = wdk_failure(
            "POST", "/refreshed-dependent-params", 422, recorded.raw_text()
        )

        # UNSPECIFIED marks a sentence somebody wrote, to show verbatim.
        assert "UNSPECIFIED" in str(error)

    def test_wdk_valid_006_by_key_names_the_parameter(self) -> None:
        body = (
            '{"level":"SEMANTIC","isValid":false,'
            '"errors":{"general":[],"byKey":{"organism":["Invalid value \'Nope\'."]}}}'
        )

        error = wdk_failure("POST", "/users/1/steps", 422, body)

        assert error.errors == [
            {"param": "organism", "messages": ["Invalid value 'Nope'."]}
        ]
        assert "organism" in str(error)

    def test_wdk_valid_006_a_prose_body_still_becomes_an_error(self) -> None:
        recorded = load_recorded("refresh_without_changed_param")

        error = wdk_failure(
            "POST", "/refreshed-dependent-params", 400, recorded.raw_text()
        )

        assert error.status == 400
        assert error.errors is None
        assert "'changedParam' property is required" in str(error)

    def test_wdk_valid_006_the_status_survives_the_parse(self) -> None:
        recorded = load_recorded("refresh_with_a_value_outside_the_vocabulary")

        error = wdk_failure(
            "POST", "/refreshed-dependent-params", 422, recorded.raw_text()
        )

        assert error.status == 422


def test_wdk_strat_007_a_refusal_names_the_owning_strategy() -> None:
    body = "Step 440085983 belongs to strategy 330423363 so cannot be assigned to"

    error = wdk_failure("PUT", "/users/1/strategies/2/step-tree", 422, body)

    assert error.status == 422
    assert "belongs to strategy" in str(error)


def test_wdk_step_005_the_refusal_is_prose_at_level_unspecified() -> None:
    body = (
        '{"level":"UNSPECIFIED","isValid":false,"errors":{"general":'
        '["Step 440085953 is not part of a strategy, so cannot run."],"byKey":{}}}'
    )

    bundle = validation_bundle(body)

    assert bundle is not None
    assert bundle.level == "UNSPECIFIED"
    assert bundle.errors is not None
    assert bundle.errors.by_key == {}
