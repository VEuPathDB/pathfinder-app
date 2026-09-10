"""The names this deployment is known by.

The runtime defaults to no product, so the application a request is served
under and the assistant a thread runs are named here. The four helper
strategies this deployment writes into a WDK account are named here too,
because a run and the cleanup that matches it must read one string.
"""

PATHFINDER_APPLICATION_ID = "pathfinder"
PATHFINDER_ASSISTANT_ID = "pathfinder"

# The prefix every helper strategy this deployment writes already carries.
INTERNAL_STRATEGY_NAME_PREFIX = "__pathfinder_internal__:"

_PRODUCT = "Pathfinder"

CONTROL_TEST_STRATEGY_NAME = f"{_PRODUCT} control test"
ENRICHMENT_STRATEGY_NAME = f"{_PRODUCT} enrichment analysis"
GENE_SET_STRATEGY_NAME = f"{_PRODUCT} gene set"
STEP_COUNTS_STRATEGY_NAME = f"{_PRODUCT} step counts"
