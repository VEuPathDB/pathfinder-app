---
type: Decision
title: The three libraries are consumed by URL at a commit
description: apps/api names veupathdb-py, veupathdb-mcp, assistant-core and veupathdb-mcp-conformance by repository URL and a 40-character rev, apps/web names @pathfinder/assistant-client by repository URL, workspace and commit, and the wdk-mcp image builds from the MCP repository at WDK_MCP_REV; subtree mirrors, an internal package index that does not exist, and GitHub Packages were rejected.
tags: [split, packaging, uv, yarn, docker, ci, dependencies]
generated: { by: claude-code/opus-5, at: 2026-09-06T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-06T00:00:00Z }
status: stable
---

# What was decided

The three libraries are repositories. PathFinder names each one by URL and one
commit, and nothing in this repository copies or resolves to a folder of theirs.

| Consumer | Declaration |
| --- | --- |
| `apps/api/pyproject.toml` `[tool.uv.sources]` | `{ git = <repository>, rev = <40 characters> }`, with `subdirectory` for the two packages inside the platform repository |
| `apps/web/package.json` | `git+https://github.com/VEuPathDB/ai-assistant-platform.git#workspace=@pathfinder/assistant-client&commit=<40 characters>` |
| `docker-compose.yml` `wdk-mcp` | `context: https://github.com/VEuPathDB/ai-wdk-mcp.git#${WDK_MCP_REV:?}` |

A pin is a commit, never a branch. A branch moves under a lock that claims to
have resolved it, and the same checkout then builds two different images on two
days. A repository that adopts the `v<version>` tag convention may be named by
its tag instead; a tag is exact in the same way a commit is.

To take a newer commit of one library:

```bash
cd apps/api
# change `rev`
uv lock --upgrade-package <name>
uv sync
```

For the TypeScript client, change `commit=` and run `yarn install` at the root.
For the `wdk-mcp` image, set `WDK_MCP_REV` in the env file.

# What follows from it

**A library's own pins reach the resolver.** uv reads `tool.uv.sources` out of a
dependency that is itself a source tree, so the MCP repository's row for the
client is resolved against its own checkout. The two repositories must therefore
name the client the same way, and `[tool.uv] override-dependencies` in
`apps/api/pyproject.toml` states the app's pin for every dependent while they
disagree.

**A document that a consumer asserts against must ship in a distribution.**
`PROTOCOL.md` lives at `packages/assistant-core/src/assistant_core/PROTOCOL.md`,
so a source checkout, an editable install and a wheel all resolve it as
`Path(assistant_core.__file__).parent / "PROTOCOL.md"`. Package data placed
outside the package directory does not survive the sdist a wheel is built from.

**Both images need a client that can clone.** `apps/api/Dockerfile` and
`apps/web/Dockerfile` install `git` in the stage that resolves dependencies. The
three repositories are public, so no token is involved.

# What would falsify this

A copy of this repository made without the three folders, in which
`uv sync --frozen` fetches the three repositories and the api unit suite passes,
and `yarn install --immutable` resolves the client from `node_modules` with the
web typecheck, vitest and build green.

# What was rejected

**Subtree mirrors.** The folders stayed the source and a ritual pushed them to
the org repositories. Two copies of one tree diverge the first time a change
lands in the mirror, and the monorepo's gates keep passing while they do.

**An internal package index.** A pin of the form `veupathdb-py>=0.1.0` reads
better than a commit, and needs an index that serves these distributions.
VEuPathDB runs no such index. A dependency that cannot be resolved is not a
better dependency for reading well.

**GitHub Packages.** It has no Python index at all, so the three Python
distributions could not use it. Its npm registry requires a token even for a
public package, which puts a credential in every clone, every CI job and every
image build for one dependency.

When a real index appears, each `[tool.uv.sources]` row becomes a version
specifier in `[project].dependencies`, the client's entry becomes a version, and
the `wdk-mcp` context becomes an image tag. The pins are the only lines that
change.
