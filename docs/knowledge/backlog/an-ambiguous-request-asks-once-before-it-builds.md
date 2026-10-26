---
type: Backlog
title: An ambiguous request asks once with counts before it builds
description: Branch worktree-agent-a293400e9888ebfc7 holds the reviewed change that asks one question, with each reading's count, before BUILD when a request's readings give different results; it ships after a live run confirms it asks for ambiguous requests and stays quiet for clear ones.
tags: [lead, frame, consult, readings]
generated: { by: claude-code/opus-5.5, at: 2026-10-26T00:00:00Z }
status: proposed
---

# An ambiguous request asks once with counts before it builds

## What happens

The branch (commits 758cc3129, 03307fb02, eaa95dfe9 and the round that closes the typed-words binding holes) asks once per request, before BUILD, with counted options, a union option for alternative searches, a coverage option for 'all of X', a remember offer for a picked definition, and a setting that uses the recommended reading. It passed review except the last round's items. It was not merged because the QA sites were down and the change alters how the Lead and FRAME behave.

## Done when

Live run on QA: an 'all of a genus' request and a single-copy request each ask one card before any build, and the answer builds once with no repeated discovery; a concept with several definitions asks with a union option and offers to remember the pick; two clear requests ask nothing. Then merge the branch into main.
