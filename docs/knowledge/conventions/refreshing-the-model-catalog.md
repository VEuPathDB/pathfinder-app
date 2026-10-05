---
type: Convention
title: Refreshing the model catalog
description: How to take a new model or retire one. The lineup is one module, the tiers are derived from each entry's rank, and a devtool compares the catalog with what each provider serves.
tags: [models, catalog, tiers, devtools]
generated: { by: claude-code/opus-5, at: 2026-09-28T00:00:00Z }
status: stable
---

# Where the lineup lives

`apps/api/src/pathfinder/platform/model_catalog.py` is the one module that names a
model id. Each `ModelEntry` carries its prices, its two measured attachment
flags and its `rank` in its provider's lineup: `flagship`, `standard` or
`small`. Each cloud provider holds one `is_provider_default` entry, one
`small` entry and at most one entry per rank; `validate_lineup` refuses any
other lineup at import. `DEFAULT_MODEL_ID` is the OpenAI default entry, and
every role's compile-time model and the injection judge read it.

`platform/tiers.py::derive_tiers` reads the ranks. Each tier names a model for
the planning roles (Lead, FRAME) and one for the worker roles (BUILD, VERIFY,
site help): quality runs the flagship at high over the standard entry at
medium; balanced the standard entry over the small one, both at medium;
default runs the provider's default entry at medium for every role; fast
runs the small entry at low for every role. VERIFY checks at high on the
worker model in every tier.
A missing rank takes the next rank down, and a tier whose roles land on one
entry runs it at the planning roles' effort. Tests read ids through
`tests/_support/models.py`, the web tests through
`apps/web/src/lib/models/__fixtures__/models.ts`.

# The steps

1. Run the check with the deployment's keys in the environment:
   `uv run python -m pathfinder.devtools.model_catalog check`. It lists the
   catalog entries a provider no longer serves (exit 1), the served ids of a
   catalog family the catalog does not hold, and the date the prices were
   last read.
2. Edit the lineup in `model_catalog.py`: add, remove or re-rank entries, and move
   `is_provider_default` to flip a provider's default. Read each price from the
   provider's pricing page.
3. Measure the two attachment flags of a new entry:
   `uv run python -m pathfinder.devtools.model_catalog probe <id>`. It sends a
   plain request at medium effort, one 1x1 PNG and one one-page PDF, and prints
   `supports_images` and `supports_documents`. A refusal the provider files as
   no credit measures the account, not the model; leave the flag `false`.
4. Bump `PRICES_AS_OF`.
5. Edit the decided tables in `tests/unit/platform/test_tier_derivation.py` and
   `tests/unit/platform/test_model_catalog.py`, and the two fixture modules if an id
   they hold left the lineup. Run the unit tier.
6. Run `uv run python -m pathfinder.devtools.model_catalog record` to refresh
   `tests/fixtures/provider_models/`, and `yarn generate:types` from the root if
   `ModelEntry` changed shape.
7. Check that `genai-prices` prices the new ids
   (`assistant_core.pricing.lookup_per_mtok_prices`). A model it does not know
   is metered at zero, so take a release of it that does
   (`uv lock --upgrade-package genai-prices`).
