---
type: Decision
title: The assistant platform is a grouping of three distributions, not one
description: packages/{assistant-core, assistant-client-ts, mcp-conformance} and PROTOCOL.md moved into a repository of their own with a README naming the three and the contract between them; merging them into one distribution was rejected because they ship to different consumers on different release clocks and in two languages.
tags: [assistant-core, assistant-client, mcp-conformance, split, architecture, packaging, protocol]
generated: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
status: stable
---

# What was decided

`VEuPathDB/ai-assistant-platform` holds three distributions that already stood
alone, plus the document that binds two of them:

| folder | distribution | import name |
| --- | --- | --- |
| `packages/assistant-core/` | `assistant-core` | `assistant_core` |
| `packages/assistant-client-ts/` | `@pathfinder/assistant-client` | - |
| `packages/mcp-conformance/` | `veupathdb-mcp-conformance` | `mcp_conformance` |

The move is a folder rename and nothing else: **zero import lines changed**,
because none of the three ever imported through a path. What changed is every
path that named them - the two `[tool.uv.sources]` rows, five `COPY` lines, the
root `package.json` workspace entry, the `files:` patterns of eight pre-commit
hooks, twenty CI `working-directory` values, `pyrightconfig.json`, the two
`vitest` configs, `apps/web/tsconfig.json`, and the client's `sync:protocol`
script.

`PROTOCOL.md` is package data of the runtime,
`packages/assistant-core/src/assistant_core/PROTOCOL.md`, because a consumer
that asserts against a document has to receive it with the distribution; see
[the libraries are consumed by URL](the-libraries-are-consumed-by-git-url.md).
It is still the contract **between** two of the three, and both readers follow
it: `assistant-core`'s `test_protocol_document.py` compares it against the
chunks the runtime emits, and the client's `tests/conformance/` compares it
against the capture `yarn sync:protocol` produces. A change to the document that
neither side implements fails both.

# Why a grouping and not one distribution

**The rejected alternative is merging them into a single distribution.** One
pyproject, one version, one release. It fails on what each is for:

- `assistant-core` is a Python runtime a host application installs.
- `@pathfinder/assistant-client` is a TypeScript package a browser bundles. It
  cannot be a Python distribution at all, so a merge would leave two anyway.
- `mcp-conformance` is an admission suite a deployment runs against a server it
  did **not** build. Shipping it with the runtime would mean a deployment that
  wants to read a third-party tool server installs the whole turn pipeline.
  [The conformance suite is a separate
  distribution](the-conformance-suite-is-a-separate-distribution.md) already
  ruled on this.

Their release clocks differ for the same reason: the protocol is versioned
additively and a client bump is not a runtime bump.
[Assistant-core is a package boundary](assistant-core-is-a-package-boundary.md)
and [the runtime is a package](the-runtime-is-a-package.md) hold unchanged; this
decision only says where the three folders live and that the protocol sits above
them.

# The folder is the TypeScript client's Yarn project

The two Python packages each carry a `uv.lock`, so each resolves alone. The
TypeScript client carried none: its resolution lived in the monorepo root's
`yarn.lock`, and installed anywhere else it took whatever a fresh resolve
picked. `assistant-platform: package.json` is now a private Yarn root declaring
`packages/assistant-client-ts` as its only workspace, pinning the same Yarn
release the monorepo root pins, with its own `.yarnrc.yml` and `yarn.lock`;
`yarn install --immutable` is the first step of the client's lane in
`assistant-platform: .github/workflows/ci.yml`, and
`assistant-platform: .pre-commit-config.yaml` carries the same hooks the root
config runs for these three packages.

The monorepo root's `workspaces` does not name the client. `apps/web` reaches it
as a Yarn dependency on the platform repository, selecting the workspace and one
commit; see
[the libraries are consumed by URL](the-libraries-are-consumed-by-git-url.md).
`apps/web` compiles the packed `dist`, so it needs no second install and no
`tsconfig` path into the client's source.

`ai` is pinned to `6.0.154` in the client's own lock, and its peer range stops
below `6.0.250`, because that release changed `resumeStream` so a resumed stream
is a fresh response rather than a continuation of the assistant message the
client already holds. `PROTOCOL.md` section 6.1 requires the opposite: a turn
suspended on a durable task closes with `finish`, and the gap's
`data-task-progress` and `data-task-completed` chunks belong to that turn's
message. Two `tests/conformance/resumedTurn.test.ts` cases fail on `ai` 6.0.271
for exactly that reason, so the failure is the newer library changing a
behaviour the protocol relies on and not a harness accident. Adopting the newer
resume semantics means reducing the tail outside the SDK and merging it into the
held message, which is a client redesign; it is
[a backlog item](../backlog/adopt-the-new-ai-sdk-resume-semantics.md), not a
silent pin.

# What the grouping is not

It is not one distribution with shared tooling. Each package keeps its own lock,
its own gates and its own CI job, and `assistant-core`'s suite still runs with no
application installed. The `packages/` directory that remains in PathFinder
holds `spec` and `shared-ts`, which are generated from the FastAPI app and
belong to it.
