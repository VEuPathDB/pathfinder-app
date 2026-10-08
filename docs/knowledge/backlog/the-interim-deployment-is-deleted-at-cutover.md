---
type: Backlog
title: The interim deployment is deleted at the cutover
description: BLOCKED on the estate stack serving the development site. Delete the GHCR workflow, the rootless units and their installer with every check, hook and document that names them.
tags: [deployment, cutover, ci, quadlets, cedar]
generated: { by: claude-code/opus-5.5, at: 2026-10-08T00:00:00Z }
status: proposed
---

# The interim deployment is deleted at the cutover

**Blocked on the estate stack.** The estate's units serve PathFinder from
`docker.io/veupathdb` once the systems team deploys them
([the images decision](../decisions/the-images-come-from-the-registry-and-cedar-pulls.md)).
Until the development site answers `/pathfinder/` from that stack, the tester
host keeps the rootless units and the GHCR images. Stopping the rootless stack
on the host is the user's call.

**The work, in one change:**

- Delete `.github/workflows/publish-images.yml`, `quadlets/`,
  `deploy/cedar/` (its `install.sh`, `README.md` and env examples) and
  `README-podman-quadlets.md`.
- `scripts/check-release.mjs`: drop the workflow from `MCP_CONTEXT_FILES`, with
  its fixture and its test in `scripts/check-release.test.mjs`;
  `.pre-commit-config.yaml`: drop it from the `release` hook's `files` pattern.
  Otherwise the check fails reading a file that is gone.
- Delete `scripts/check-quadlets.mjs` and its test, its CI job and its
  `ci-status` entry, its pre-commit hook and its `CLAUDE.md` gate-list entries;
  both paths it reads are gone. The same for the quadlet halves of
  `apps/api/src/pathfinder/tests/unit/platform/test_deployment_env_guards.py`.
- Rewrite the interim paragraphs of
  [the images decision](../decisions/the-images-come-from-the-registry-and-cedar-pulls.md)
  and of [the traces decision](../decisions/traces-go-to-langfuse-over-plain-otlp.md),
  the README's CD line, and every other file that names a quadlet, `deploy/cedar`
  or the workflow
  (`grep -rln "quadlets/\|deploy/cedar\|publish-images" docs/knowledge README.md apps scripts .github`).

**Done when** the root and api gates pass with none of those paths present and
the grep above finds only `docs/knowledge/log.md`.
