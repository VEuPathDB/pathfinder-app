---
type: Decision
title: The three libraries are consumed by URL at a release
description: apps/api names veupathdb-py, veupathdb-mcp, assistant-core and veupathdb-mcp-conformance by repository URL and a release tag, apps/web names @veupathdb/assistant-client the same way, and the wdk-mcp image builds from the same release, committed in its compose build context
tags: [split, packaging, uv, yarn, docker, ci, dependencies]
generated: { by: claude-code/opus-5, at: 2026-09-06T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-06T00:00:00Z }
status: stable
---

# What was decided

The three libraries are repositories. PathFinder names each one by URL and one
commit, and nothing in this repository copies or resolves to a folder of theirs.
On 2026-09-06 the folders `veupathdb-py/`, `veupathdb-mcp/` and
`assistant-platform/` were deleted from this repository, so the repositories are
the only copy.

| Consumer | Declaration |
| --- | --- |
| `apps/api/pyproject.toml` `[tool.uv.sources]` | `{ git = <repository>, tag = <release> }`, with `subdirectory` for the two packages inside the platform repository |
| `apps/web/package.json` | `git+https://github.com/VEuPathDB/ai-assistant-platform.git#workspace=@veupathdb/assistant-client&tag=<release>` |
| `docker-compose.yml` `wdk-mcp` | `context: https://github.com/VEuPathDB/ai-wdk-mcp.git#v0.1.0a3`, committed beside the Python pin |

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

For the TypeScript client, change `tag=` and run `yarn install --no-immutable`
at the root; the root enables immutable installs, so a plain install refuses to
rewrite the lock for the new pin. A release that renames the package moves the
dependency key and the `workspace=` name with the tag.
For the `wdk-mcp` image, change the tag in its compose build context, in the same
commit as the Python pin, so the served tools and the imported ones agree.

# What follows from it

**A library's own pins reach the resolver.** uv reads `tool.uv.sources` out of a
dependency that is itself a source tree, so the MCP repository's row for the
client is resolved against its own checkout. A row naming a sibling path fails
the lock here, because the path leaves the checkout. The two repositories
therefore name the client by the same URL and the same `rev`, and a bump of the
client is two commits: the MCP repository first, then this one.

**A document that a consumer asserts against must ship in a distribution.**
`PROTOCOL.md` lives at `packages/assistant-core/src/assistant_core/PROTOCOL.md`,
so a source checkout, an editable install and a wheel all resolve it as
`Path(assistant_core.__file__).parent / "PROTOCOL.md"`. Package data placed
outside the package directory does not survive the sdist a wheel is built from.

**Both images need a client that can clone.** `apps/api/Dockerfile` and
`apps/web/Dockerfile` install `git` in the stage that resolves dependencies. The
three repositories are public, so no token is involved.

# What would falsify this

A fresh copy of this repository in which `uv sync --frozen` fetches the three
repositories and the api unit suite passes, and `yarn install --immutable`
resolves the client from `node_modules` with the web typecheck, vitest and build
green.

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
