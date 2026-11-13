"""The names this deployment is known by.

The runtime defaults to no product, so the application a request is served
under and the assistants a thread can run are named here. The helper
strategies this deployment writes into a WDK account are named here too,
because a run and the cleanup that matches it must read one string.
"""

from strategist import __version__

APPLICATION_ID = "pathfinder"
STRATEGIST_ASSISTANT_ID = "pathfinder"
AUDIT_ASSISTANT_ID = "audit"

VEUPATHDB_USER_AGENT = (
    f"PathFinder/{__version__} (+https://github.com/VEuPathDB/pathfinder-app)"
)

INTERNAL_STRATEGY_NAME_PREFIX = "__strategist_internal__:"

# Helper strategies an earlier name of this deployment wrote, longest first.
FORMER_INTERNAL_STRATEGY_NAME_PREFIXES = (
    "__pathfinder_internal__:Pathfinder ",
    "__pathfinder_internal__:Strategist ",
    "__pathfinder_internal__:",
)

CONTROL_TEST_STRATEGY_NAME = "control test"
STEP_COUNTS_STRATEGY_NAME = "step counts"
SEPARATION_STRATEGY_NAME = "control separation"
