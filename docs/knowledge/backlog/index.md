# Backlog

Everything known to be outstanding, ranked by what actually moves the product. Each item stands alone: a fresh session should be able to pick one up without this conversation.

Items are removed when done, not marked done. The [log](../log.md) records
what left.

## Ranked

1. [The test tree is type-checked by nothing](the-test-tree-is-type-checked-by-nothing.md) - mypy 1158 / pyright 1486 errors over `apps/api/src/pathfinder/tests`; a widened library type left a live assertion silently wrong until it ran.
2. [An option criterion binds no parameter](an-option-criterion-binds-no-parameter.md) - FRAME records a parameter-option choice as a criterion, but `build_step_tree` mints steps only for what the structure names, so the option never reaches the search WDK runs.

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
