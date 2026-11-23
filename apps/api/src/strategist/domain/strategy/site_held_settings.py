"""The step settings a site holds; a saved strategy's id is held only here."""

from veupathdb.domain.strategy import StepSettings

SITE_HELD_SETTINGS = frozenset(StepSettings.model_fields) - {"expanded_strategy_id"}

__all__ = ["SITE_HELD_SETTINGS"]
