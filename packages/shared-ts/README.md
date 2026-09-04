## `@pathfinder/shared` (TypeScript) -- `packages/shared-ts`

Shared TypeScript types used by the web app and any TS tooling around the API. Most of what this
package exports is generated from the OpenAPI spec; `types.ts` is the thin hand-written layer on
top.

### What lives here

```
src/
  index.ts       # Package entry point: re-exports types.ts plus DEFAULT_STREAM_NAME
  types.ts       # The hand-written layer: aliases over generated types, the data-part
                 #   kind union, site helpers
  defaults.ts    # DEFAULT_STREAM_NAME
  generated/     # Kubb output from packages/spec/openapi.json. Do NOT edit.
    types/       #   One module per schema and per operation
    zod/         #   Runtime validators mirroring those types
    hooks/       #   React Query options and mutation hooks, one per operation
    index.ts     #   Barrel over all three
```

### Key exports

**Aliases over generated types**: `Step`, `Strategy`, `GeneSet`, `ControlSet`, `Search`,
`RecordType`, `ParamSpec`, `ModelCatalogEntry`, `GeneSearchResult`. These name the wire type the
backend actually serves, so a backend rename is a compile error here.

**Combine operators**: the generated `combineOpEnum` / `CombineOp` (the seven WDK operators),
re-exported here, and `CombineOpBadgeLabels`, the label the UI shows for each.

**Strategy AST**: the generated `StrategyAst`, `StrategyStepNode` and `ColocationParams` - the tree
of search, combine and transform nodes the UI edits - re-exported here.

**Data parts**: `KnownDataPartKind` (every `data-*` chunk the thread knows how to draw) and
`DataPartKind` (that union, open to kinds an assistant adds). The frontend's renderer map must be
total over `KnownDataPartKind`.

**Site types**: the generated `SiteResponse`, plus `siteDisplayName` and `siteShortName`.

**Zod validators**: `generated/zod/` carries one schema per wire type. `lib/api/http.ts` in the web
app validates every response against them at the network boundary.

### How the web app imports these

The web app uses TS path mapping (`@pathfinder/shared`) configured in `apps/web/tsconfig.json`.
Next.js transpiles this package automatically via `transpilePackages` in `next.config.ts`.

### Common commands

```bash
cd packages/shared-ts
yarn build            # tsc
yarn typecheck        # tsc --noEmit
yarn format:check     # prettier --check
```

Regenerate from an already-dumped spec:

```bash
yarn generate         # kubb
```

To refresh the spec itself from the application and regenerate in one step, run
`yarn generate:types` from the repo root.

Check that the generated output matches the committed spec, which is what CI does:

```bash
yarn check:generated  # kubb && tsc --noEmit
```
