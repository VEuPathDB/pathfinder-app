---
type: Decision
title: The docs build creates its extra="allow" models before autodoc runs
description: conf.py imports fastapi.openapi.models, langchain_core.messages and strategist.transport.http.schemas.sites before Sphinx starts, because autodoc's type-comment pass writes pydantic.BaseModel.__pydantic_extra__ back into BaseModel.__annotations__ and every later model with extra="allow" then fails to build; accepting the 40 empty pages and patching Sphinx's private merge function were both rejected.
tags: [docs, sphinx, pydantic, python-314]
generated: { by: claude-code/opus-5, at: 2026-08-31T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-31T00:00:00Z }
status: stable
---

# What was found

`uv run sphinx-build -b html docs docs/_build/html` reported 40 warnings of the
form `autodoc: failed to import 'chat' from module
'strategist.transport.http.routers'`, each ending in `NameError: name 'Dict' is
not defined`. All 40 targets on `docs/api/transport.rst` rendered their
hand-written prose and no API. The same modules import without error outside
Sphinx.

The chain, measured by bisecting the toctree down to a single directive:

1. Sphinx documents any class. `_ensure_annotations_from_type_comments` walks
   that class's MRO and, for each class's module, parses the module source and
   merges the source annotation text into the live class:
   `cls.__annotations__ = dict(inspect.getannotations(cls))` then
   `annotations.setdefault(attrname, annotation)`.
2. `pydantic/main.py` declares `__pydantic_extra__: Dict[str, Any] | None`, and
   `ModelMetaclass.__new__` clears `BaseModel.__annotations__` so that
   declaration never reaches a subclass. Step 1 puts it back, as the string
   `'Dict[str, Any] | None'`.
3. Pydantic evaluates that string in the namespace of the model being built,
   not in `pydantic.main`. The first model afterwards that declares
   `extra="allow"` in a module without `Dict` raises `NameError`. FastAPI's
   `BaseModelWithConfig` is such a model, so `import fastapi` fails, so every
   module that imports FastAPI fails.

`strategist.platform.errors.ProblemDetail.model_config` is the first attribute
the build documents that reaches `pydantic.main` through an MRO. Three modules
sit on the wrong side of that point: `fastapi.openapi.models`,
`langchain_core.messages` and `strategist.transport.http.schemas.sites`.

Sphinx 9.1.0 is the newest release on PyPI, and it carries the merge. The
reload the earlier reading blamed is not involved: `_import_module`'s
`try_reload` branch is gated on `SPHINX_AUTODOC_RELOAD_MODULES`, which is unset.

# The decision

`apps/api/docs/conf.py` imports those three modules immediately after it
extends `sys.path`, before Sphinx loads any extension. Their models are then
already built when the merge happens, and the merge cannot reach a model that
exists. The build reports 0 import warnings and `transport.rst` renders 925 API
objects across its 40 modules.

A regression is loud: a new `extra="allow"` model in a module without `Dict`
brings its own `failed to import` warnings back, and the warning count is the
measurement the docs cards are scored on.

# Rejected

**Accept the 40 warnings until upstream parses 3.14.** This was the standing
proposal. It costs the entire HTTP transport page plus
`strategist.ai.conversation.dispatcher`, and there is no upstream fix to wait
for: the interaction is between Sphinx's merge, pydantic's namespace choice and
FastAPI's model, and none of the three is doing anything its own tests reject.

**Patch Sphinx.** Replacing `_ensure_annotations_from_type_comments` with a
no-op removes the cause outright, and this project has no type comments for the
pass to add. It was rejected because the name is private, `_loader.py` binds it
at import time so two module attributes must be patched, and a docs config that
reaches into a build tool's internals rots without warning on the next upgrade.
Disconnecting the `autodoc-before-process-signature` listener was measured and
does not work: the `_dynamic` loader calls the merge directly, so the warning
count stayed at 40.

**Import `strategist.main`.** One line instead of three, and it covers the
whole application graph. It was rejected because `strategist.main` builds the
app at import time, which validates `API_SECRET_KEY` and `DATABASE_URL`. The
`build-docs` CI job sets no environment, so the import would abort the build
rather than warn.
