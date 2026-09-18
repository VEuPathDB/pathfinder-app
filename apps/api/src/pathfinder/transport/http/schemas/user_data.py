"""The purge endpoint's response shape."""

from assistant_core.platform.pydantic_base import CamelModel


class PurgeCounts(CamelModel):
    """What one purge destroyed, and what it could not."""

    strategies: int
    wdk_strategies: int
    wdk_strategies_kept: int
    memories: int
    gene_sets: int
    experiments: int
    control_sets: int
    staged_eval_cases: int


class PurgeUserDataResponse(CamelModel):
    """The answer to a purge request."""

    ok: bool
    deleted: PurgeCounts
