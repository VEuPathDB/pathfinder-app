---
type: Decision
title: Audits are offered on the dev sites only
description: The gene model audit is offered on a site whose host starts with muharram. and nowhere else; the site list says so, the web shows no Audits section elsewhere and the dispatcher refuses an audit thread; a deployment flag and a release-build argument were rejected.
tags: [audit, deployment]
generated: { by: claude-code/opus-5.5, at: 2026-11-08T00:00:00Z }
status: stable
---

# What was decided

A site offers the gene model audit when the host of its service address starts with `muharram.`
(`domain/audit/offered.py::offers_audits`). `GET /api/v1/sites` carries `offersAudits` for each
site. The web reads it for the current site (`useCurrentSite`): the nav rail lists Audits only
there, and every page under `/audits` shows "The gene model audit is not offered on this site."
anywhere else (`app/(app)/audits/layout.tsx`). The dispatcher refuses a turn of the audit
assistant on any other site, or on a request that names no site, with 403 `AUDITS_NOT_OFFERED`
(`services/audit/offered.py::require_audits_offered`).

# Why

The audit is a prototype that reads whole genomes; QA, beta and production serve researchers and
testers who should not start one. The dev sites are the only ones on those hosts, so the site
address already says where the audit belongs, and the same release image runs on every stage.

# What was rejected

- **A deployment flag.** One more setting per stage that a promotion can carry the wrong way.
- **A build argument that leaves Audits out of release images.** QA, beta and production run
  release tags, but the rule would live in the Jenkinsfile, far from the code it hides.
