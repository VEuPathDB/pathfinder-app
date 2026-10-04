---
type: Backlog
title: A reply never repeats a refusal it corrected
description: A Lead reply can tell the researcher that its own earlier card was refused and replaced, which is internal and means nothing to them.
tags: [lead, reply, cards]
generated: { by: claude-code/opus-5, at: 2026-10-04T00:00:00Z }
status: proposed
---

# A reply never repeats a refusal it corrected

**What I did.** On toxodb, corpus case `an-edit-to-a-sibling-strain-binds-it`,
second turn: "Switch the organism to Toxoplasma gondii GT1 on both steps."

**What I got.** The reply opened: "The earlier clarification card was malformed
because its options did not bind a strategy value. I have replaced it with a
free-text design question so you can state whether to make that biological
substitution."

**Why that's wrong.** The researcher never saw the refused card; the sentence
describes a retry inside the turn and pushes the actual question down.

**Why it happens.** A refused card's correction stays in the Lead's context, and
nothing keeps the reply from narrating it.

**Fix.** Hold the reply to what the researcher saw: no clause about a card or a
call the turn refused and replaced.

**What you'd get.** The reply asks the GT1 question directly.
