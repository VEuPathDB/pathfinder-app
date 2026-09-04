---
type: Decision
title: The WDK service layer holds functions, not re-exports
description: services/wdk/__init__.py stopped aliasing twenty-four names out of integrations.veupathdb; the client handouts became real service functions, every legal caller imports the defining module, and the one type edge that is left is four named lines in the layering contract with a test pinning the symbol. Moving the whole wire-model module into domain/ was rejected for now because it rewrites 176 import statements.
tags: [architecture, import-linter, wdk, services]
generated: { by: claude-code/opus-5, at: 2026-09-03T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-03T00:00:00Z }
status: stable
---

# What was found

`services/wdk/__init__.py` was seventy lines of `from
pathfinder.integrations.veupathdb... import ...` plus a twenty-four name
`__all__`. Its own docstring said why: so that "AI tools and other higher-level
consumers import from `services.wdk` instead of reaching into
`integrations.veupathdb` directly".

That is the layering contract satisfied by an alias. The name a caller imported
was the integration's own object, so `VEuPathDBClient`, `StrategyAPI` and
`TemporaryResultsAPI` were one import away from any tool or any route, and
nothing checked which of the twenty-four a caller took. Eleven of the
twenty-four had no importer at all.

Most importers did not need it. A service may import an integration, so
`services/catalog`, `services/conversations`, `services/strategies`,
`services/tool_payloads` and `pathfinder/mcp` were routing through an alias to
reach something they were always allowed to name.

# The decision

The package exports nothing. `services/wdk/__init__.py` is an empty file.

- **Every caller that may import an integration does.** The service modules and
  the MCP server name `pathfinder.integrations.veupathdb.factory`,
  `.discovery_service`, `.discovery` and `.wdk_models` directly.
- **The client handouts became functions with a caller's signature.**
  `services/wdk/step_results.py::step_results_service` builds the reader for one
  built step, so a route no longer constructs a `StrategyAPI`.
  `services/wdk/step_preview.py` owns the two reads a tool renders directly, and
  the agent tool and the MCP tool now share them.
  `services/wdk/login.py` owns opening and ending a VEuPathDB session.
- **A wire scalar that transport needs moved to the domain layer.**
  `WDKSortDirection` is defined in `domain/wdk_values.py`, beside the record-id
  and histogram shapes that were already there for the same reason.
- **The one edge that is left is stated, not laundered.** Four FRAME tool
  modules annotate a WDK search definition with `WDKSearch`, and the layering
  contract names those four imports in `ignore_imports`.

# Why the last edge is not closed here

`WDKSearch` is a frozen response model that opens no connection, and it belongs
where every layer may name it: `pathfinder/domain/`. It cannot go alone. Its
fields reference `WDKModel`, `WDKParameterGroup`, `WDKSortSpec`,
`WDKAttributeField` and the `WDKParameter` discriminated union, so the move is
`integrations/veupathdb/wdk_models.py` plus `wdk_parameters.py`, which 176
import statements across 176 modules name. That is one serialized change of its
own, not a rider on this one.

The rejected alternative was to keep the facade until then. It reads as the
smaller step and it is the worse one: the facade hides the exception, admits
every other name in the integration along with it, and gives a reader no way to
see that four modules and one type are the whole debt.

# Anchor

`apps/api/pyproject.toml` holds the contract and its four ignored edges.
`apps/api/src/pathfinder/tests/unit/services/wdk/test_no_integration_facade.py`
reads every module under `ai/` and `transport/` off the syntax tree and fails
any import from `pathfinder.integrations` that is not `WDKSearch` from
`wdk_models`, and fails a `services/wdk/__init__.py` that holds anything at all.
The contract cannot see a symbol; that test can, so the exception cannot grow
into a client. Done when the wire models live in `domain/`, the four lines leave
the contract, and the test's allowed set is empty.
