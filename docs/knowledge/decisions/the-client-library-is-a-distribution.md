---
type: Decision
title: The client library is a distribution, so PathFinder cannot reach into it
description: pathfinder/{veupathdb, integrations/veupathdb, integrations/eda} and the WDK-shaped half of domain/ moved out of apps/api into a repository of its own with its own pyproject, lock, tests, README, knowledge bundle and CI lane, consumed as an editable path dependency; import-linter contracts 1 and 4 were deleted and replaced by the package's dependency list plus its own boundary suite. Keeping the client in-repo behind import contracts was rejected, because the owner is publishing the folder as its own GitHub repository.
tags: [veupathdb-py, split, architecture, packaging, import-linter, wdk, eda]
generated: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
status: stable
---

# What was decided

The VEuPathDB client is its own repository: its own `pyproject.toml`, its own lock
file, a `src/veupathdb` layout importable with no `pathfinder.` prefix, its own
test tree with a hermetic lane and a live lane, its own README, its own copy of
the WDK and EDA knowledge bundle with the two check scripts that keep it honest,
and `apps/api` consuming it as an editable path dependency. This is the shape
[the runtime is a package](the-runtime-is-a-package.md) already argued for, applied
to the second unit.

The mapping is a prefix rename and nothing else:

| was | is |
| --- | --- |
| `pathfinder.veupathdb` | `veupathdb` |
| `pathfinder.integrations.veupathdb` | `veupathdb.wdk` |
| `pathfinder.integrations.eda` | `veupathdb.eda` |
| `pathfinder.domain.{parameters,strategy,search,wdk_values,eda_study,eda_filter_checks}` | `veupathdb.domain.*` |
| `pathfinder.devtools.{wdk_fixtures,eda_schemas,pins}` | `veupathdb.devtools.{fixtures,eda_schemas,pins}` |

`sites.yaml` ships inside the wheel and is read through
`importlib.resources.files("veupathdb")`; `VEUPATHDB_SITES_CONFIG` still overrides it.
`veupathdb.testing` holds what a host's own tests import: the recorded-fixture reader,
the WDK test-account credential reader and the live lane's drift log.

# The proof

```
cd veupathdb-py && rm -rf .venv && uv sync --frozen && uv run pytest tests/unit
```

in a shell where PathFinder is not installed. A module that imported `pathfinder`
would fail to resolve, not fail a lint rule. `tests/unit/test_package_boundary.py`
walks every module and asserts the same thing per module, so the failure names the
module rather than the run.

# What it replaced

Import-linter contract 1 ("Domain layer is pure") and contract 4 ("Integrations never
import services, transport, or AI") are deleted. Contract 1 is now the package's
dependency list plus `test_the_domain_opens_no_connection`. Contract 4's surviving
half - the embedding index does not reach up into services - moved out of this
distribution with the index itself; see [the MCP server is a
distribution](the-mcp-server-is-a-distribution.md), which deleted the empty
`pathfinder.integrations` package. Contract 2 keeps the persistence half and loses
the four `ignore_imports` that named `wdk_models`: a third-party module needs no
exemption.

# The accepted risk: the authoring model ships in the client

`veupathdb.domain.strategy` carries PathFinder's authoring model, not WDK's:
`operational_spec.py`, `constraints.py`, `spec_diff.py`, `session.py` and
`combination_check.py`. They ship here because `veupathdb.wdk` imports them, measured
as 12 edges into `ast`, 10 into `ops`, 8 into `tree`, 7 into `graph_model`, 5 into
`session` and 5 into `operational_spec`. A second consumer of `veupathdb-py` would find
them puzzling. The cost of cutting them out is that `veupathdb/wdk/**` must stop naming
them, which is a refactor of the client's own call sites and not a folder move; it is
[a backlog card](../backlog/re-cut-the-authoring-model-out-of-veupathdb-py.md).

# What was rejected

**Keep the client inside `apps/api` behind import contracts.** This is what the two
deleted contracts did, and it held for as long as one repository held everything. The
owner is publishing `veupathdb-py` as its own GitHub repository, so a rule a linter
applies inside one checkout proves nothing about the artifact anyone installs.

**Split the knowledge bundle by subject.** Rejected after measuring: 15 rule blocks and
39 `status` lines name PathFinder code, and the WDK model prose cites the rules they
belong to, so a subject split breaks 51 fields and 15 citations. What moved is the
whole WDK and EDA bundle; what stayed is `wdk/pathfinder/`, whose eight `WDK-MAP` rules
are invariants of the application rather than facts about WDK. A rule the library cannot
enforce locally is `UNENFORCED` there with a `reason` naming the consumer's test.

# Publishing

Done. The library is `VEuPathDB/ai-veupathdb-client`, and `apps/api` names it by
URL at a commit; see
[the libraries are consumed by URL](the-libraries-are-consumed-by-git-url.md).
