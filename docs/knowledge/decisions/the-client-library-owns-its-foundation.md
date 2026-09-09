---
type: Decision
title: The client library owns its foundation, so no edge points up out of it
description: The 84 imports from the future veupathdb-py module set into assistant_core and pathfinder.platform were deleted or inverted in place - a base model, a JSON alias, a logger, an error taxonomy, a settings read, a context variable, a metrics sink and four catalog modules - leaving 0. A fifth shared distribution was rejected, because a 20-line base class duplicated in two libraries is cheaper than a package everyone has to install.
tags: [veupathdb, split, architecture, packaging, errors, settings, observability]
generated: { by: claude-code/opus-5, at: 2026-09-04T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-04T00:00:00Z }
status: stable
---

# What was decided

The module set that becomes the `veupathdb` client distribution -
`integrations/veupathdb/**`, `integrations/eda/**`, `domain/{parameters,
strategy,search,wdk_values}` and the `domain/eda*` modules - imports nothing
above itself. It reached `assistant_core` 56 times and `pathfinder.platform`
28 times; both counts are now 0. The files did not move. A later folder move
is then a prefix rename, `veupathdb` -> `veupathdb`, and nothing
else; an edge that still pointed up could not be renamed.

The foundation those modules rest on is a new package,
`veupathdb-py: src/veupathdb/`. It was the only place both
`pathfinder.domain` and `pathfinder.integrations` could import from under the
layer contracts of the time, because contract 1 forbade domain -> integrations.
Its names carry no underscore: the other two units import them too.

**The four kinds of upward edge, and what replaced each.**

1. *A shape the library declares.* `CamelModel` became
   `veupathdb/model.py`, the JSON aliases became `veupathdb/json_types.py`,
   and `strip_html_tags` became `veupathdb/text.py` (`platform/text.py` is
   deleted). Each is a copy, not a re-export. `assistant_core` keeps its own.

2. *A host service the library called directly.* `get_logger` became
   `veupathdb/logging.py`: `structlog.get_logger(name)` bound to
   `structlog.BoundLogger` and nothing else. A library binds a logger; it
   never configures one. `setup_logging`, which installs processors and
   handlers, stays with the host, and a boundary test fails any unit-1 module
   that calls `structlog.configure`.

3. *A host fact the library read.* `veupathdb/settings.py` declares
   `VEuPathDBSettings(BaseSettings)` with `veupathdb_sites_config` and
   `veupathdb_auth_token`, plus `use_veupathdb_settings_source` /
   `get_veupathdb_settings`. `pathfinder.platform.config.Settings` now
   subclasses both `RuntimeSettings` and `VEuPathDBSettings` and installs
   itself into both sources at import time, so one settings instance still
   serves the whole process and the env var names are unchanged. No unit-1
   module computes a path to `config.toml`. `veupathdb_auth_token_ctx` moved
   down into `veupathdb/auth_context.py` and is gone from
   `platform/context.py`.

4. *A host instrument the library fed.* The six OpenTelemetry counters and
   histograms became an `Observer` protocol in `veupathdb/observer.py` with a
   `NoObserver` default and a module-level `set_observer`.
   The adapter over the same meters is the client's own optional extra
   (`veupathdb-py: src/veupathdb/observability/otel.py`), and `main.py`'s
   lifespan installs it beside `setup_observability` - the only place a
   `MeterProvider` is configured, so no process lost a metric. The instrument
   names and the full attribute sets are asserted in
   `veupathdb-py: tests/unit/test_otel_observer.py`.

**The error taxonomy split by who raises it.** `veupathdb/errors.py` holds
`VEuPathDBError`, a `VEuPathDBErrorCode(StrEnum)`, and the classes the client
raises: `ValidationError`, `WDKError`, `WDKLoginRequiredError`,
`ExternalServiceError`, `DataParsingError`, plus `validate_response` and
`param_message_rows`. `platform/errors.py` keeps `AppError`, `ProblemDetail`
and the whole 29-member `ErrorCode`, because that enum is the wire. One
handler, `veupathdb_error_handler`, maps a library refusal to a
`ProblemDetail` under `ErrorCode(exc.code.value)` and the exception's own
status, so no response changed and the OpenAPI spec is unchanged.

`VEuPathDBErrorCode` has seven members, not the six the split design
proposed: `WDK_ERROR`, `WDK_LOGIN_REQUIRED`, `SITE_NOT_FOUND`,
`EXTERNAL_SERVICE_ERROR`, `VALIDATION_ERROR`, `DATA_PARSING_ERROR`,
`INTERNAL_ERROR`. The rule is what the library actually raises. It raises all
seven - `site_router.py` raises `SITE_NOT_FOUND`, `strategy_api/analyses.py`
raises `INTERNAL_ERROR`, and the `ValidationError` and `DataParsingError`
classes carry the other two. It does not raise `SEARCH_NOT_FOUND` or
`INVALID_PARAMETERS`: those are raised in `veupathdb_mcp/catalog` and
`services/conversations`, which are not in the unit. Every one of the seven
string values equals an `ErrorCode` member, and a test walks the whole enum
through the handler.

**Four catalog modules moved down, not sideways.** `discovery.py`,
`discovery_service.py`, `disk_cache.py` and `catalog_metadata.py` are a
catalog snapshot and a semantic index, not a WDK client. They moved from
`integrations/veupathdb/` to what is now `veupathdb_mcp/catalog/`, and
`get_discovery_service` moved out of `integrations/veupathdb/factory.py` with
them, so `factory.py` now imports no embeddings, no sqlalchemy, no readiness and
no task spawner. Contract 4, "integrations never import services", was green
because the move was downward; the contract and the layer are both gone now.

**The snapshot the two images share now names its format.** `api` and
`wdk-mcp` exchange a catalog snapshot through the `catalogs_cache` volume.
`disk_cache.SNAPSHOT_FORMAT_VERSION` is written into every snapshot, and a
read of a snapshot whose version differs, or that carries none, is refused
with a warning naming both versions; the caller then rebuilds as if the cache
were cold. Without it the first field change would have one image reading
another image's file as if it were its own.

# What was rejected

**A fifth shared distribution holding `CamelModel`, the JSON aliases and the
logger.** It removes the duplication, and the duplication is real: a 15-line
base class and a 7-line alias module now exist in both `assistant_core` and
`veupathdb`. It was rejected on the same ground as `RuntimeSettings` in [the
runtime is a package](the-runtime-is-a-package.md): a package that every one
of four distributions must install, version and release in order to spell
`model_config = ConfigDict(alias_generator=to_camel)` costs more than writing
that line twice. KISS over DRY where the extraction is larger than what it
extracts.

**Keeping `veupathdb_auth_token_ctx` in `platform/context.py`.** The runtime
decision left it there, reasoning that its taxonomy names WDK bearers and so
belongs to the application. That reasoning inverts once the client is its own
distribution: the client *is* the thing that names WDK bearers, and it is the
only reader of the variable that cannot be handed the value as an argument -
`_http.py` reads it per request, below every call site. Leaving it up would
have kept a `pathfinder.platform` import in the client's transport module,
which is exactly the edge this batch exists to remove. The host still writes
it, from `platform/security.py` and from the worker's `attach_wdk_auth`.

**Shipping `prometheus_client` or `opentelemetry` as a library dependency.**
Rejected because a client library must not own a global metrics registry. The
observer seam lets a host with no telemetry at all install nothing and pay a
no-op call.

# What would falsify this

`veupathdb-py: tests/unit/test_package_boundary.py` walks every module of the
installed distribution with `pkgutil`, parses each with `ast`, and fails on an
import whose root is `pathfinder`, `assistant_core`, `veupathdb_mcp`,
`sqlalchemy`, `asyncpg`, `pgvector`, `pydantic_ai`, `langgraph`, `fastapi`,
`fastmcp`, `prometheus_client` or `opentelemetry`. It also fails any module
that calls `structlog.configure`, any `veupathdb.domain` module that opens a
connection or names `veupathdb.wdk` or `veupathdb.eda`, and any import in the
two wire-model modules other than `pydantic`. That suite is the acceptance
criterion; the day it needs an exception, an edge has come back.

`uv run python -m pathfinder.devtools.openapi check` fails if the error split
changed a `ProblemDetail` code or a status. `uv run lint-imports` fails if the
catalog move reverses.

The MCP server's module set imports this foundation rather than duplicating it;
see [the MCP server writes no PathFinder table](the-mcp-server-writes-no-pathfinder-table.md).
