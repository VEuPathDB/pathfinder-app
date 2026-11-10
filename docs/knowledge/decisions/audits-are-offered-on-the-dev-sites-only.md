---
type: Decision
title: Audits are offered on the dev sites only
description: The gene model audit is offered on a site whose host starts with muharram. and nowhere else; the site list says so, the web shows no Audits section elsewhere, the dispatcher refuses an audit thread, and the strategy-building assistant holds no audit tool; a deployment flag, a release-build argument and a second copy of the rule in begin_run were rejected.
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

The audit is an internal VEuPathDB tool, offered only through the audit assistant. The
strategy-building assistant (the Lead) holds no audit tool: it plans, starts and reads no run
and investigates no gene model. A message the reader classes `gene_model_audit` is answered in
one sentence that says the strategy builder runs no audit, and no audit is offered. The audit
assistant's tools are the only way an audit starts, so the dispatcher's refusal is the one gate
this rule needs.

# Why

The audit is a prototype that reads whole genomes; QA, beta and production serve researchers and
testers who should not start one. The dev sites are the only ones on those hosts, so the site
address already says where the audit belongs, and the same release image runs on every stage.

# What was rejected

- **A deployment flag.** One more setting per stage that a promotion can carry the wrong way.
- **A build argument that leaves Audits out of release images.** QA, beta and production run
  release tags, but the rule would live in the Jenkinsfile, far from the code it hides.
- **A second copy of the rule in `services/audit/job.py::begin_run`.** Every caller of
  `begin_run` is a tool of the audit assistant, whose turns the dispatcher already refuses off
  the dev sites, so a second check would guard no entry point the first does not.
- **The Lead's audit tools withheld off the dev sites.** The Lead held the audit tools until
  the audit was made the audit assistant's alone; withholding them by site would keep a second
  entry point to one assistant's work and a second copy of the rule.
