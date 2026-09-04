from pathfinder.ai.agents._history_compaction import compact_exhausted_history
from pathfinder.ai.agents._history_elision import elide_consumed_tool_results
from pathfinder.ai.agents._history_pairing import pair_tool_calls

PHASE_HISTORY_PROCESSORS = (
    pair_tool_calls,
    elide_consumed_tool_results,
    compact_exhausted_history,
)
