"""The names this deployment is known by.

The runtime defaults to no product, so the application a request is served
under and the assistants a thread can run are named here. The helper
strategies this deployment writes into a WDK account are named here too,
because a run and the cleanup that matches it must read one string.
"""

PATHFINDER_APPLICATION_ID = "pathfinder"
PATHFINDER_ASSISTANT_ID = "pathfinder"
SITE_HELP_ASSISTANT_ID = "site_help"

# The prefix every helper strategy this deployment writes already carries.
INTERNAL_STRATEGY_NAME_PREFIX = "__pathfinder_internal__:"

_PRODUCT = "Pathfinder"

CONTROL_TEST_STRATEGY_NAME = f"{_PRODUCT} control test"
STEP_COUNTS_STRATEGY_NAME = f"{_PRODUCT} step counts"
SEPARATION_STRATEGY_NAME = f"{_PRODUCT} control separation"
