---
type: Decision
title: A study another site publishes is not opened here
description: On a component site, an EDA study whose publishing sites do not include that site is listed with its site label and a sentence naming where to ask, and the bind refuses it in the tool and in the HTTP route before any analysis is written. The portal opens every study, and the researcher's own upload always opens on its site. Rejected - hiding such studies from the search, opening them and warning after, and refusing only at the step export.
tags: [eda, cross-site, agents, transport]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: stable
---

# What was decided

This is the EDA twin of [another site's experiment informs a criterion and
never binds](another-site-informs-and-never-binds.md). The EDA service serves
the portal's study catalog on every site, so a search on plasmodb ranks
mosquito studies beside Plasmodium ones. A step exported from a study joins
its gene ids to the current site's genes, so a study the site does not publish
exports a step that is empty by construction.

**The rule is one pure function.**
`services/eda/study_site.py::not_here(site_id, sites, own=...)` answers None
when the study opens on `site_id`, and otherwise the sentence

> This study is on VectorBase; its genes are not PlasmoDB genes. Ask on
> VectorBase.

It answers None on the portal, for the researcher's own upload, when `sites`
holds `site_id`, and when `sites` is empty (the store did not answer, so
nothing is known). A study no genomics site publishes carries `["portal"]` and
names "the VEuPathDB Portal". Site names come from the site list
(`get_site(...).name`).

**The bind refuses before anything is written.**
`services/eda/binding.py::bind_analysis` calls
`refuse_a_study_another_site_publishes` after it resolves the dataset and
before it creates the upstream analysis. The refusal reads the publishing
sites with the tool server's `sites_publishing`. A study nobody publishes on a
genomics site is refused; a store that does not answer is a 503
(`StudySitesUnreadableError`), not an open. Every surface that binds goes
through this function: the Lead's `open_eda_analysis`, which turns the refusal
into a retry that carries the sentence, and the tab's
`PATCH /conversations/{id}/eda` bind action, which answers 422 with the
sentence as `detail`.

**The search informs.** `search_eda_studies` and `GET /eda/studies` list such a
study with its `sites` and its `notHere` sentence. The tool guidance says a
study with `notHere` cannot be opened here and that the researcher gets its
sentence. The picker draws the row disabled, with the sentence under it.

# Rejected

- **Hiding studies another site publishes from the search.** The researcher
  asked a question another site answers; an empty list hides that route. The
  sentence names the site to ask on.
- **Opening the study and warning after.** The analysis document is written to
  the researcher's workspace and the export is still empty, so the warning
  arrives after the harm.
- **Refusing only at the step export.** A subset and a comparison on the study
  take minutes of compute that no step on this site can use.
- **Opening a study whose sites cannot be read.** The store is the only source
  of the publishing sites, so an open without it can still export an empty
  step; an unanswered read is reported as unavailable instead.
