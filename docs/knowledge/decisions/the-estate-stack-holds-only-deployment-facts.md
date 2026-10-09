---
type: Decision
title: The estate stack holds only deployment facts
description: The estate units run both MCP servers from the pathfinder-api image with a command of their own, read each stage's sites file from that image, and set only the values that differ from the code's defaults or name the stage, so a PathFinder release needs no change to the services repository. A separate MCP tag in the stack's environment and MCP images built from this repository's Jenkinsfile were rejected.
tags: [deployment, quadlets, docker, jenkins, mcp, sites]
generated: { by: claude-code/opus-5.5, at: 2026-10-09T00:00:00Z }
status: stable
---

# What was decided

A release of PathFinder is a tag of this repository and nothing else. The units in
`VEuPathDB/webservices-quadlets` change only when the deployment changes: a host, a
secret, a network, a memory limit.

**Both MCP servers run from the api image.** The api image installs `veupathdb-mcp`
at the release `apps/api/pyproject.toml` pins, so the estate's `pathfinder-wdk-mcp@`
and `pathfinder-research-mcp@` units run `docker.io/veupathdb/pathfinder-api:${PATHFINDER_TAG}`
with `Exec=.venv/bin/python -m veupathdb_mcp` and `Exec=.venv/bin/python -m veupathdb_mcp.research`.
The servers are always the release the api imports in process, and `tagger` promotes
two images, `pathfinder-api` and `pathfinder-web`. Each MCP unit keeps a `HealthCmd`
of its own, because the image's `HEALTHCHECK` probes the api port.

**Each stage's sites file is in the api image.** `deploy/sites/dev.yml` and
`deploy/sites/qa.yml` are copied to `/app/config/sites/`, and the stage's override
file sets `VEUPATHDB_SITES_CONFIG` to its own. A new site URL is a commit here.
`tests/unit/test_the_stage_sites_files.py` holds the site ids and the hosts of each
stage.

**The stack's environment holds what the code cannot know.** A variable stays in
`env/00-pathfinder_defaults.env` only when it names the stage or the stack (the image
tag, the auto-update policy, the database names, the public address, the sites file,
the service names on the stack network, the Crossref mailbox) or differs between two
containers (the catalog refresh and the index sync). A tuning change is a change to a
default in this repository or its libraries. What every stage runs with and the code
cannot default is set by the api image itself: `API_ENV=production`, over the
`development` its `config.toml` holds for a host run; `PATHFINDER_CHAT_PROVIDER=default`,
because an empty value fails startup; and `VEUPATHDB_INTERNAL_STRATEGY_NAME_PREFIX`,
because the wdk-mcp container otherwise reads the client's own prefix and not
PathFinder's.

# What would falsify this

A stage whose MCP servers report another version on `/health` than the
`veupathdb-mcp` the api has installed; a PathFinder release that cannot reach a stage
without a change to the services repository; or a stage that serves another site list
than its file under `deploy/sites/`.

# What was rejected

**A separate MCP tag in the stack's environment.** The stack read `PATHFINDER_MCP_TAG`
for the two MCP images that the `ai-wdk-mcp` job publishes. Every release that moved
the pin then needed a pull request to the services repository, in step with the
release, and `tagger` had to promote four images as a matched pair.

**MCP images built from this repository's Jenkinsfile.** The images would carry the
names `pathfinder-wdk-mcp` and `pathfinder-research-mcp`, which the `ai-wdk-mcp` job
already publishes. Two jobs that push one name overwrite each other, and changing the
other job needs the systems team. The `ai-wdk-mcp` job stays as it is; this stack does
not use its images.
