---
type: Decision
title: One build moves up the ladder
description: One branch builds each image once. A push to main reaches dev as latest, a version tag publishes a build, and the tagger moves an environment tag to it, through a commit on qa and beta and a pull request on prod. A branch per environment and a version that names its stage were rejected.
tags: [release, deployment, jenkins]
generated: { by: claude-code/opus-5.5, at: 2026-11-04T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-11-04T00:00:00Z }
status: stable
---

# What was decided

The environments, in order: dev, qa, prod beta, prod live.

| Step | What moves | How |
|---|---|---|
| Dev | `:latest` | A push to `main`; Jenkins builds it and the dev stack follows |
| Publish a build | `:0.9.0-b1` | A tag `v0.9.0-b1`; it runs nowhere new |
| QA or beta | `:qa`, `:beta` | A commit to that branch of `VEuPathDB/tagger` |
| Prod | `:prod` | A pull request to the tagger's protected `prod` branch |

The tagger's `versions.yml` maps an image to a version, and its build retags that image with
the branch's name, so a stage runs the image the stage before it ran. Rollback is a revert in
the tagger.

`scripts/release.mjs` holds the steps:

```bash
node scripts/release.mjs bump 0.9.0-b2
node scripts/release.mjs tag 0.9.0-b2
node scripts/release.mjs promote qa 0.9.0-b2          # shows the change
node scripts/release.mjs promote qa 0.9.0-b2 --push   # makes it
```

A version is `0.9.0-bN` on the way to prod, spelled `0.9.0bN` in the api, and `1.0.0` is the
first live release.

# What was rejected

**A branch per environment.** Each branch builds its own image, so a stage would run a build the
stage before it never ran, and fixes would merge between branches. A `qa` that gates `main` also
puts qa before dev, because the dev stack follows `main`.

**A version that names its stage, such as `0.9.0-qa3`.** The same image moves up, so the name goes
false on the first promotion. PEP 440 also has no `qa` pre-release, so the api could not hold it.

# What would prove this wrong

`scripts/release.test.mjs` holds the version spelling, the tagger edit and the stages.
`scripts/check-release.mjs` refuses a tag that does not name the api version.
