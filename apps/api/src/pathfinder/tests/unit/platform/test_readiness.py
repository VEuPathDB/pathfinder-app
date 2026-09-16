"""Tests for the ReadinessState model."""

import pytest

from pathfinder.platform.readiness import (
    ReadinessState,
    SubsystemStatus,
    get_readiness,
    reset_readiness,
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_readiness()


def _process_ready() -> ReadinessState:
    """Every fixed subsystem ready, no catalog registered yet."""
    state = ReadinessState()
    state.mark_ready("database")
    state.mark_ready("embedding_backend")
    state.mark_ready("graph_checkpointer")
    return state


class TestSubsystemStatus:
    def test_default_not_ready(self) -> None:
        status = SubsystemStatus()
        assert status.ready is False
        assert status.error is None

    def test_ready_with_no_error(self) -> None:
        status = SubsystemStatus(ready=True)
        assert status.ready is True
        assert status.error is None

    def test_error_implies_not_ready(self) -> None:
        status = SubsystemStatus(ready=False, error="boom")
        assert status.ready is False
        assert status.error == "boom"


class TestReadinessState:
    def test_fresh_state_is_not_ready(self) -> None:
        state = ReadinessState()
        assert state.all_ready is False
        assert "database" in state.not_ready
        assert "embedding_backend" in state.not_ready
        assert "graph_checkpointer" in state.not_ready

    def test_all_ready_requires_every_subsystem(self) -> None:
        state = _process_ready()
        state.register_catalog("plasmodb")
        state.mark_catalog_ready("plasmodb")
        assert state.all_ready is True
        assert state.not_ready == []
        assert state.degraded == []

    def test_one_ready_catalog_is_enough(self) -> None:
        state = _process_ready()
        state.register_catalog("plasmodb")
        state.register_catalog("veupathdb")
        assert state.all_ready is False

        state.mark_catalog_ready("plasmodb")
        assert state.all_ready is True

    def test_a_registered_catalog_that_is_not_ready_is_degraded(self) -> None:
        state = _process_ready()
        state.register_catalog("plasmodb")
        state.register_catalog("veupathdb")
        state.mark_catalog_ready("plasmodb")
        state.mark_catalog_failed("veupathdb", TimeoutError())

        assert state.degraded == ["veupathdb"]
        assert state.not_ready == []

    def test_a_catalog_still_loading_is_degraded(self) -> None:
        state = _process_ready()
        state.register_catalog("plasmodb")
        state.mark_catalog_ready("plasmodb")
        state.register_catalog("veupathdb")

        assert state.degraded == ["veupathdb"]

    def test_no_ready_catalog_is_not_ready(self) -> None:
        state = _process_ready()
        state.register_catalog("plasmodb")
        state.mark_catalog_failed("plasmodb", TimeoutError())

        assert state.all_ready is False
        assert state.not_ready == ["catalogs"]

    def test_no_registered_catalog_is_not_ready(self) -> None:
        state = _process_ready()

        assert state.all_ready is False
        assert state.not_ready == ["catalogs"]

    def test_a_failed_subsystem_outranks_a_ready_catalog(self) -> None:
        state = _process_ready()
        state.mark_failed("embedding_backend", "OSError")
        state.register_catalog("plasmodb")
        state.mark_catalog_ready("plasmodb")

        assert state.all_ready is False
        assert state.not_ready == ["embedding_backend"]

    def test_degraded_catalog_carries_the_last_error(self) -> None:
        state = _process_ready()
        state.register_catalog("veupathdb")
        state.mark_catalog_failed("veupathdb", TimeoutError())

        degraded = state.degraded_catalog("veupathdb")
        assert degraded is not None
        assert degraded.error == "the site did not answer in time"

    def test_a_ready_catalog_is_not_degraded(self) -> None:
        state = _process_ready()
        state.register_catalog("plasmodb")
        state.mark_catalog_ready("plasmodb")

        assert state.degraded_catalog("plasmodb") is None
        assert state.degraded == []

    def test_an_unregistered_site_is_not_degraded(self) -> None:
        state = _process_ready()

        assert state.degraded_catalog("plasmodb") is None
        assert state.catalogs == {}

    def test_the_first_loaded_catalog_is_named_in_id_order(self) -> None:
        state = _process_ready()
        for site_id in ("veupathdb", "toxodb", "plasmodb"):
            state.register_catalog(site_id)
        state.mark_catalog_ready("toxodb")
        state.mark_catalog_ready("plasmodb")

        assert state.first_ready_catalog == "plasmodb"

    def test_no_loaded_catalog_names_nothing(self) -> None:
        state = _process_ready()
        state.register_catalog("veupathdb")

        assert (state.first_ready_catalog, state.degraded) == (None, ["veupathdb"])

    def test_mark_failed_sets_error_and_keeps_not_ready(self) -> None:
        state = ReadinessState()
        state.mark_failed("database", "connection refused")
        assert state.database.ready is False
        assert state.database.error == "connection refused"
        assert "database" in state.not_ready

    def test_fail_loading_marks_every_subsystem_still_loading(self) -> None:
        state = ReadinessState()
        state.mark_ready("database")
        state.register_catalog("plasmodb")
        state.fail_loading(ZeroDivisionError("warm-up died"))
        assert state.database.ready is True
        assert state.embedding_backend.error == "ZeroDivisionError: warm-up died"
        assert state.graph_checkpointer.error == "ZeroDivisionError: warm-up died"

    def test_fail_loading_gives_a_catalog_the_error_class_alone(self) -> None:
        """The sites response reports this value, so it carries no message."""
        state = ReadinessState()
        state.register_catalog("plasmodb")
        state.fail_loading(ZeroDivisionError("https://plasmodb.org refused"))
        assert state.catalogs["plasmodb"].error == "its catalog did not load"

    def test_fail_loading_keeps_an_error_a_step_already_reported(self) -> None:
        state = ReadinessState()
        state.mark_failed("embedding_backend", "connection refused")
        state.mark_catalog_failed("plasmodb", ConnectionResetError())
        state.fail_loading(ZeroDivisionError("warm-up died"))
        assert state.embedding_backend.error == "connection refused"
        assert state.catalogs["plasmodb"].error == "the site could not be reached"

    def test_unknown_subsystem_raises(self) -> None:
        state = ReadinessState()
        with pytest.raises(ValueError, match="unknown"):
            state.mark_ready("does_not_exist")

    def test_singleton_returns_same_instance(self) -> None:
        a = get_readiness()
        b = get_readiness()
        assert a is b

    def test_reset_clears_state(self) -> None:
        state = get_readiness()
        state.mark_ready("database")
        assert state.database.ready is True
        reset_readiness()
        assert get_readiness().database.ready is False


class TestTheOptionalScreeningSubsystem:
    """A deployment that screens nothing reports no screening subsystem."""

    def test_an_unreported_screener_holds_no_traffic(self) -> None:
        state = _process_ready()
        state.register_catalog("plasmodb")
        state.mark_catalog_ready("plasmodb")

        assert state.input_screening is None
        assert state.not_ready == []
        assert state.all_ready is True

    def test_a_ready_screener_is_reported_and_holds_nothing(self) -> None:
        state = _process_ready()
        state.register_catalog("plasmodb")
        state.mark_catalog_ready("plasmodb")
        state.mark_ready("input_screening")

        assert state.input_screening == SubsystemStatus(ready=True)
        assert state.not_ready == []
        assert state.all_ready is True

    def test_a_failed_screener_holds_the_process_and_carries_its_error(self) -> None:
        state = _process_ready()
        state.register_catalog("plasmodb")
        state.mark_catalog_ready("plasmodb")
        state.mark_failed("input_screening", "OpenAIError: Missing credentials")

        assert state.not_ready == ["input_screening"]
        assert state.all_ready is False
        assert state.input_screening == SubsystemStatus(
            ready=False,
            error="OpenAIError: Missing credentials",
        )
