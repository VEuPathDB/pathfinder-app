---
type: Decision
title: The dead-code checker is a pinned dependency, and its whitelist is one config line
description: vulture is declared in the api dev group and wired into the pre-commit hook and the Lint API job, because 2.16 on Python 3.14 parses the whole tree; deleting the checker was rejected, the 49-entry vulture_whitelist.py was deleted because at min_confidence 80 it changed nothing, and min_confidence 60 was rejected at 997 findings.
tags: [gates, dead-code, python-314, tooling]
generated: { by: claude-code/opus-5, at: 2026-08-31T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-31T00:00:00Z }
status: stable
---

# What was decided

`vulture` is a declared dev dependency of `apps/api`, pinned `>=2.16`, and it
runs in two places that must stay identical: the `vulture-api` hook in
`.pre-commit-config.yaml` and the `Check for dead code` step of the `Lint API`
job in `.github/workflows/ci.yml`. Both spell it `uv run vulture`, which reads
`[tool.vulture]` in `apps/api/pyproject.toml`. `vulture_whitelist.py` is
deleted. The one suppression the tree needs is a single `ignore_names` entry.

# The checker parses Python 3.14; the invocation did not

The reported failure was 69 `invalid syntax` lines over valid PEP 758, PEP 695
and `match` code. It was not vulture's parser. `[tool.vulture]` was configured
but vulture was in no dependency group, so `uv run vulture` fell through the
project environment to a global install:

```
$ uv run vulture --version
vulture 2.14
$ uv run which vulture
/Users/<home>/anaconda3/bin/vulture
```

That interpreter predates 3.14. The current release inside the project
environment reads every file:

```
$ uv run --with 'vulture' vulture --version
vulture 2.16
$ uv run --with 'vulture' vulture src/strategist --exclude 'tests/,*/conftest.py' --min-confidence 80
7 findings, 0 lines containing "invalid syntax", exit 3
```

So the fix is to declare the tool, not to replace or remove it. **Deleting
`[tool.vulture]` outright was the rejected alternative**: a checker that reads
the whole tree in 2 seconds and blocks a merge is worth the one line, and the
evidence for deletion was an artifact of an unpinned binary.

# The whitelist was deleted because it decided nothing

`vulture_whitelist.py` held 49 names. `min_confidence` is 80, and vulture
scores an unused function, method, class or attribute at 60, so none of those
49 names could ever have been reported. The run with the file removed from
`paths` returns the same 7 findings as the run with it. 16 of the 49 named
symbols had no `def` left anywhere in `apps/api/src` or `packages/*/src`.

A file that is maintained by hand, cannot change an outcome, and rots is worse
than no file. Its live replacement is one entry:

```toml
ignore_names = ["CursorResult"]
```

Six imports of `CursorResult` are read as unused because every use is inside
`cast("CursorResult[object]", ...)`. Ruff rule `TC006` requires that type
expression to be a string, and vulture does not resolve string annotations. The
imports are load-bearing: mypy and pyright resolve the string. Unquoting the
casts to satisfy vulture would fail ruff, so the name is ignored instead.

# min_confidence stays at 80

Lowering it to 60 is what would make vulture report unused functions and
classes, which is the dead code ruff cannot see. Measured on this tree that is
**997 findings at 60% confidence** - every FastAPI handler, Pydantic validator,
agent tool and SQLAlchemy column, all reached by dispatch vulture cannot trace.
That is a whitelist the size of the API surface, and it is the file this
decision just deleted, restored an order of magnitude larger. Rejected.

At 80 the gate reports unreachable code, unused imports and unused variables,
and its value is the seams ruff's per-file analysis does not cover. It is not a
replacement for ruff `F401`.
