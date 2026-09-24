## Pathfinder Web (`apps/web`)

Next.js UI for PathFinder. It provides:

- **Chat interface**: a durable, resumable thread that renders the agent's reply, its tool trace, its figures and its background tasks
- **Strategy graph editing**: visual strategy builder with node/edge operations, combine steps, and parameter editing
- **EDA**: exploratory subsetting and visualization of study data
- **Evidence in the thread**: control tests, comparisons and gene-set figures, each with its own actions (a gene set can be published to VEuPathDB or deleted)

### Project structure

```
src/
  app/                          # Next.js App Router
    [siteId]/                   #   Every user-facing route is site-scoped
      (app)/conversation/       #     Thread, and its strategy / EDA panes
      (app)/saved/              #     Saved strategies
    api/v1/chat/                #   The one hand-written proxy route (chat POST)
    api/telemetry/              #   Browser telemetry sink
    components/                 #   App-level shell components
    hooks/                      #   App-level hooks
    providers/                  #   Client providers (query, theme, telemetry)
    layout.tsx page.tsx not-found.tsx
  components/                   # Vendored primitives, not written here
    ui/                         #   shadcn components (the `components.json` target)
    ai-elements/                #   Vendored chat primitives
  features/                     # Feature modules (vertical slices)
    conversation/               #   The thread
      ChatShell -> ChatView -> ChatThread   # the three components a page mounts
      api/                      #     Query options for the thread's own endpoints
      composer/                 #     Input bar and its gates (quota, sign-in)
      slash/                    #     Slash-command popover, parser and registry
      content/                  #     Message part renderers; contentComponents.ts is the map
        parts/                  #       One component per data-* kind that draws something
      thread/                   #     Trace, figures, task rows, approval card
      rail/                     #     Right rail: ledger, tasks, memories, scratchpad, strategy, EDA
      runtime/                  #     assistant-ui runtime wiring and chat helpers context
      data/                     #     Static thread data
    eda/                        #   EDA workbench, study picker, filters, compute config
    saved/                      #   Saved strategy library
    settings/                   #   Settings modal (model, tiers, privacy, data, memory, seeding)
    sidebar/                    #   Conversation sidebar and its subtree dialogs
    sites/                      #   Site selection, banners, per-site theming
    strategy/                   #   Strategy graph and step editing
      graph/                    #     ReactFlow canvas; elkjs layout; serialize/deserialize
      editor/                   #     Step editor: bodies, widgets, schema, patch building
      operations/               #     The typed graph operation algebra and its wire form
      mutations/                #     React Query mutations for every graph edit
      parameters/               #     Parameter coercion and spec helpers
      validation/               #     Save validation, formatting, zero-result advisor
      services/ hooks/ page/
  lib/                          # Shared, not feature-specific
    api/                        #   http.ts (base request + Zod validation), client.ts,
                                #     conversations.ts, strategy.ts, sites.ts, geneSets.ts,
                                #     errors.ts, veupathdb-auth.ts
    query/                      #   React Query client, keys, hooks, invalidation, test helpers
    components/                 #   Shared shells (QueryBoundary, Modal, spinners, charts)
    color/ config/ eda/ errors/ hooks/ markdown/ models/ parameters/ sse/ telemetry/ types/ utils/
  state/                        # Global state (Zustand stores)
    useSessionStore.ts          #   Chat session state
    useSettingsStore.ts         #   User preferences
    useRightRailStore.ts        #   Right rail selection
    useAuthGateStore.ts         #   Login gate
    eda.ts                      #   EDA analysis state
    useStrategySelectors.ts     #   Strategy selector hooks
    strategy/                   #   Composed strategy store
      store.ts                  #     Store, plus the draft and meta state
      historySlice.ts           #     History/undo-redo slice
      lifecycleSlice.ts         #     Per-step lifecycle machine snapshots
      stepMachine.ts            #     The XState machine one step runs
      selectors.ts types.ts useStepSnapshot.ts
  styles/globals.css            # Tailwind imports and global styles
  typings/remark-gfm.d.ts       # Ambient type declarations
```

### Key patterns

**Feature-based organization**: each feature is a self-contained module with its own components,
hooks, services and utilities. Cross-feature imports go through `lib/` or `state/`, and
`scripts/check-boundaries.mjs` fails a build that breaks the rule.

**Generated types, not hand-written ones**: request and response types come from
`@pathfinder/shared`, whose `src/generated/{types,zod,hooks}` is produced by Kubb from
`packages/spec/openapi.json`. A type the backend changed is a compile error here, not a runtime
surprise. Do not hand-edit anything under `generated/`.

**State management**: [Zustand](https://github.com/pmndrs/zustand) stores in `state/` hold global
state. The strategy store in `state/strategy/store.ts` holds the draft and meta state directly and
composes the history and lifecycle slices. Selector hooks live in `useStrategySelectors.ts`.
Server state is React Query's, not Zustand's.

**The thread is durable**: chat streams over SSE from a durable event log.
`@ai-sdk/react`'s `useChat()` runs through `DurableChatTransport` from
`@veupathdb/assistant-client/ai-sdk`, which reads frames strictly, resumes from a stored cursor,
and replays a snapshot when there is no turn in flight. Closing the tab loses nothing.

**Message parts**: a message is an ordered `parts` array. `features/conversation/content/`
renders them; `contentComponents.ts` merges the core, strategy and EDA maps into one that must be
total over `KnownDataPartKind`, so a kind the backend adds without a renderer fails to compile.
The default thread draws tool activity as a trace with flat figures and task rows.

**Strategy graph**: graphs are drawn with [ReactFlow](https://reactflow.dev/) and laid out by
[elkjs](https://github.com/kieler/elkjs). Serialization lives in `features/strategy/graph/`
(`serialize.ts`, `deserialize.ts`), and every edit goes through the typed operation algebra in
`features/strategy/operations/` before it reaches the API.

**API validation at the network boundary**: responses are validated against Zod schemas on fetch
(`lib/api/http.ts`). Contract drift is caught at the boundary, not deep in component logic.

**Styling**: [Tailwind CSS](https://tailwindcss.com/) with utility classes. Reusable UI primitives
live in `components/ui/` (shadcn, the `components.json` target). Per-site theming is handled by
`features/sites/siteTheme.ts`.

**Real API + test-only mock LLM for E2E**: Playwright tests call live VEuPathDB APIs for gene
searches, strategy builds and catalog browsing. Only the LLM chat call is mocked, and only through the
dedicated test profile (`PATHFINDER_CHAT_PROVIDER=mock`). Worker isolation uses
`/dev/login?user_id=worker-{N}` so parallel workers do not interfere. VEuPathDB refuses guest
service calls, so every worker also carries the registered account's token in its
`Authorization` cookie: the shell exports `WDK_TEST_TOKEN`, or exports `WDK_TEST_EMAIL` and
`WDK_TEST_PASSWORD` and global setup signs in once to obtain it (CI passes those two as secrets).

**SSE over WebSocket**: chat streaming uses Server-Sent Events (unidirectional server to client)
rather than WebSockets. Messages are sent via POST; responses stream via SSE. Next.js has
compression disabled (`compress: false` in `next.config.ts`) so SSE events flush immediately.

### How it talks to the API

The web app uses Next rewrites to proxy to the backend (see `next.config.ts`), so UI requests like
`/api/...` forward to the configured API base. `app/api/v1/chat/` is the one route handled in
Next itself.

Required env:

- `NEXT_PUBLIC_API_URL` (required; see `/.env.example` or `/.env.dev.example` at the repo root)

### Run locally

```bash
cd apps/web
cp ../../.env.dev.example .env
yarn install
yarn dev
```

Open `http://localhost:3000`. The API and the worker must both be running: chat turns execute in
the worker, so without it a turn never finishes.

### Scripts

From `package.json`:

- `yarn dev`: start Next dev server
- `yarn build` / `yarn start`: production build + start
- `yarn lint`: ESLint
- `yarn format` / `yarn format:check`: Prettier
- `yarn typecheck`: TypeScript (`tsc --noEmit`)
- `yarn check:boundaries`: feature isolation
- `yarn check:weak-assertions`: assertion strength in tests
- `yarn check:strict-mode`: bans index-based Playwright locators
- `yarn test` / `yarn test:coverage` / `yarn test:watch`: Vitest
- `yarn test:e2e`: Playwright E2E tests
- `yarn test:mutation`: Stryker

### E2E testing

PathFinder uses a 3-tier Playwright E2E test architecture:

- **Feature tests** (`e2e/feature/`) - individual feature verification (chat, strategy graph, gene sets, settings). Run in parallel.
- **Cross-feature tests** (`e2e/cross-feature/`) - multi-feature workflows. Run serially due to WDK rate limits.
- **Journey tests** (`e2e/journey/`) - full researcher workflows across VEuPathDB databases. Run serially.

**Page Objects** (`e2e/pages/`) encapsulate selectors and interactions. **Fixtures**
(`e2e/fixtures/`) handle auth, API setup and test data seeding.

All tests use real VEuPathDB APIs. Only the LLM is mocked, via the dedicated test profile.

Start the local E2E stack with that profile. The e2e overlay builds the web container's `runner`
target, so port 3000 serves the production build: the suite meets no development overlay and no
per-route compile.

```bash
docker compose --env-file ../../.env.test \
  -f ../../docker-compose.yml \
  -f ../../docker-compose.dev.yml \
  -f ../../docker-compose.e2e.yml \
  up -d --build --wait api worker web
```
