---
type: Convention
title: Maintaining this bundle
description: What belongs in the knowledge bundle, what does not, and the rule that keeps it from rotting.
tags: [meta, documentation, okf]
generated: { by: claude-code/opus-5, at: 2026-08-09T00:00:00Z }
status: stable
---

# What belongs here

Four kinds of thing, and nothing else:

- **Decisions** - a choice that had a real alternative, where the reasoning is not recoverable by reading the code. "We rejected X because Y" is the whole value. If the code makes the choice obvious, do not write it down.
- **Backlog items** - work known to be outstanding, with enough context that a fresh session can pick it up cold.
- **Conventions** - how we work, where that is not already enforced by a tool.
- **WDK references** - how VEuPathDB's WDK actually behaves, and the rules PathFinder must not break. This is the one kind of reference material admitted here, and only because it has an external oracle: WDK's source and its live REST API decide whether a statement is true, so a WDK concept is falsifiable in the way this bundle demands. A WDK concept without pinned upstream evidence is inadmissible. See [decisions/upstream-is-the-falsifier.md](../decisions/upstream-is-the-falsifier.md).

# What does not belong here

- Anything `CLAUDE.md` already states. That file loads every session; duplicating it here creates two sources of truth that will disagree.
- Anything PathFinder's own code, tests, or type signatures already say. A doc that restates a function is a doc that will lie about it after the next edit. WDK's code is not ours and is not in this repository, which is the entire reason the exception above exists and the exact limit of it.
- Session narrative. "We tried X then Y then Z" belongs in the log at most, and usually nowhere.

# Update the bundle in the same change, always

Finishing a piece of work is not done until this bundle reflects it. In the same change, not afterwards and not in a summary:

- **Delete the backlog item.** Items are removed when finished, never crossed out or marked done. A backlog of struck-through lines is a graveyard, and it hides how much is actually left.
- **Remove its line from `backlog/index.md`.** `check-knowledge` fails on a dangling link and on a concept no index links to, so the file and the index cannot drift apart.
- **Write the decision** if the work settled a question with a real alternative. If it did not, do not invent one.
- **Add a log entry** saying what left the backlog and why, including work closed as won't-do.

**When everything is finished, `backlog/` holds nothing but `index.md`.** That is the definition of done for the whole effort, and it is only true if items leave as they are completed. An item discovered mid-work gets added the same way, so the backlog is what remains, at all times.

# The rule that stops it rotting

**A file here must be falsifiable, and something must falsify it.**

Every concept names the file, test, or command that would prove it wrong. When that anchor moves, the concept is stale and must be edited or deleted in the same change. A decision doc with no anchor is an opinion, and opinions rot silently.

Delete aggressively. A wrong doc is worse than a missing one, because it gets believed.

For WDK rules the anchor is mechanical: `scripts/check-wdk-rules.mjs` fails the build
when a citation is unpinned, an anchor path or symbol has moved, or a test named as
enforcing a rule no longer exists.

A page in another repository cannot be a relative link, so it is cited as that
repository's prefix, a colon, a space and the path, inside a code span: for
example `assistant-platform: docs/knowledge/conventions/verification-gates.md`,
which states the same rule for that bundle. The four prefixes
`scripts/check-knowledge.mjs` reads are `pathfinder`, `veupathdb-py`,
`veupathdb-mcp` and `assistant-platform`. It resolves the path against a
checkout of that repository beside this one, fails when the checkout has no such
path, reports the citation as unverified when there is no checkout to read, and
fails on a citation written without the space wherever it runs. A fenced block
holds no code span, so that is where the form is quoted as an example rather
than cited:

```
veupathdb-py: docs/knowledge/wdk/rules/searches-and-answers.md
```

# Shape

Per OKF v0.2:

- Every non-reserved `.md` carries YAML frontmatter with a non-empty `type`. That is the only hard requirement.
- `index.md` and `log.md` are reserved filenames and are not concepts. Only the bundle-root `index.md` carries frontmatter, and only `okf_version`.
- A concept's ID is its path within the bundle minus `.md`. So `decisions/step-status-is-derived.md` has the ID `decisions/step-status-is-derived`.
- Cross-links are ordinary markdown links, relative between files. They are untyped and directed; the surrounding prose carries the meaning.
- Actors follow the OKF convention: `human:<id>` for people, `<producer>/<version>` for agents, `process:<id>` for automation. Consumers read the `human:` prefix to tell a reviewed concept from a generated one.

`status` is `draft`, `stable`, or `deprecated`. Use `deprecated` rather than deleting when a decision was reversed and the reversal itself is worth knowing.

# House style

ASCII punctuation only. No em-dashes, no unicode ellipsis, in prose and in code strings alike.
