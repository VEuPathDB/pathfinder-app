---
type: Backlog
---

# The test tree is type-checked by nothing

**What I did.** Ran the two type checkers over `apps/api/src/pathfinder/tests`
after a live test asserted `>` on a field that had become `int | None`
(`tests/live/test_ai_expression_reporter.py:173`) and neither gate noticed.

**What I got.** `mypy --strict src/pathfinder/tests`: 1158 errors in 124 files
(9.4 s). `pyright src/pathfinder/tests`: 1486 errors in 115 files (16.4 s), of
which 10 are `reportOptionalOperand`, the one rule that would have caught it.

**Why that's wrong.** A library release that widens a field type leaves every
test that compares the old type silently wrong until a live run reads a value
the test never expected; the unit gates stay green because they never see the
comparison on the new type.

**Why it happens.** `[tool.mypy]` in `apps/api/pyproject.toml` and the repo-root
`pyrightconfig.json` scope both checkers to `src` minus the tests tree.

**Fix.** Bring the tests tree under one checker rule by rule, starting with
`reportOptionalOperand` and the strict-optional family, until the whole tree
is green; then add the tree to the gate in every definition (`pyproject.toml`,
`pyrightconfig.json`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`)
and the CLAUDE.md command list.

**What you'd get.** A test comparing a nullable count without binding it is
refused at the gate, before a live run.
