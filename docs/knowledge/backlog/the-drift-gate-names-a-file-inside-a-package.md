---
type: Backlog
title: The embedder drift gate imports a file inside a tool-server package
description: tests/unit/platform/test_embedder_copies_agree.py imports veupathdb_mcp.embeddings.embedder, the only import in this repository that names a file rather than a package, although every name it reads is already published on veupathdb_mcp.embeddings.
tags: [testing, embeddings, veupathdb-mcp, layering]
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
status: stable
---

# What I did

Read `apps/api/src/pathfinder/tests/unit/platform/test_embedder_copies_agree.py`
and compared the names it imports against what the tool server publishes in
`veupathdb-mcp: tests/unit/published_surface.json`.

# What I got

Line 18 is `import veupathdb_mcp.embeddings.embedder`, a file inside a package.
It is used twice: line 44 takes
`Path(veupathdb_mcp.embeddings.embedder.__file__).resolve().parent` as the
directory to compare, and line 83 reads
`veupathdb_mcp.embeddings.embedder.EMBEDDING_DIMENSIONS`.

The published surface file names 13 surfaces. `veupathdb_mcp.embeddings` is one
of them, and it already publishes `EMBEDDING_DIMENSIONS` and `FakeEmbedder`,
which the same test reads off the package on line 96. The package's own
`__file__` resolves to the same directory line 44 wants.

# Why that's wrong

The tool server publishes the names a host may read, and a file path is not one
of them: a rename or a split inside `veupathdb_mcp/embeddings/` that keeps every
published name intact still breaks this repository's test collection, and the
failure reads as a broken gate rather than as a rename. This is the only import
in the repository that reaches inside a package of that distribution, so it is
also the one exception a reader has to learn.

# Why it happens

The test names the module it compares instead of the package that publishes the
module's contents.

# Fix

In this repository, no library change. Import `veupathdb_mcp.embeddings`, take
the comparison directory from that package's `__file__`, and read
`EMBEDDING_DIMENSIONS` off the package as the test already reads `FakeEmbedder`.
The runtime copy on line 13 stays as it is: `assistant_core/embeddings/__init__.py`
exports nothing, so there is no package name to read it through.

# What you'd get

A drift gate that still compares the two copies of the embedder file by file
and reaches them through published names only, so no import in this repository
names a file inside another distribution's package.
