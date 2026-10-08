# Backlog

Everything known to be outstanding, ranked by what actually moves the product. Each item stands alone: a fresh session should be able to pick one up without this conversation.

Items are removed when done, not marked done. The [log](../log.md) records
what left.

## Ranked

1. [The Claude model is probed for images and documents](the-claude-models-are-probed-for-images-and-documents.md) - BLOCKED on keys: the OpenAI and Gemini keys answer; the probe runs on `claude-haiku-4-5` when the Anthropic account holds credit and the user says so.
33. [The interim deployment is deleted at the cutover](the-interim-deployment-is-deleted-at-cutover.md) - BLOCKED on the estate stack serving the development site: delete the GHCR workflow, `quadlets/` and `deploy/cedar/` with `check-quadlets`, their hooks, CI jobs and documents, and drop the workflow from `check-release.mjs`.
12. [A dependent pick's label is the vocabulary it was bound under](a-dependent-picks-label-is-the-vocabulary-it-was-bound-under.md) - a dependent pick is labelled under its own parents on the bind, on hydration and on replay; the site-default count still reads a dependent pick at the published default, and no recorded dependent pick has a non-empty published default yet.

31. [A message that commands a change is an edit when it also asks a question](a-message-that-commands-a-change-is-an-edit.md) - a command beside a question can be classified a question that withdraws nothing, and the turn answers read-only.
29. [A decision model is chosen on our own scorecards](a-decision-model-is-chosen-on-our-own-scorecards.md) - PARKED: Cloudflare's open-weight Clef and Clef-flash take Jev's request shape; the five Jev scorecards are rerun on both, on hosted Workers AI, before any decision model is wired.

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [One injection judge, and what a failed judgement means](../decisions/one-injection-judge-and-what-a-failed-judgement-means.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
