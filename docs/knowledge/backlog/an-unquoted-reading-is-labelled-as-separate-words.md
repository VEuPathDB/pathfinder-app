---
type: Backlog
title: An unquoted reading is labelled as separate words
description: The alternative reading of a quoted text term is labelled as the phrase although it is the word reading, and a second alternative is built from the requirement's sentence instead of the bound term.
tags: [facts, text-search, measurements]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# An unquoted reading is labelled as separate words

**What I did.** On tritrypdb, bound `GenesByText` with the quoted term `"GPI anchored"` and, as a UNION arm, `"variant surface glycoprotein"`.

**What I got.** Facts: `as "GPI anchored": 1 gene; as phrase GPI anchored: 12` and `as "variant surface glycoprotein": 768 genes; as whose product is variant surface glycoprotein: 987`, with `the site search finds 1,067 genes for "variant surface glycoprotein"` from `set_criterion`'s measurements. WDK: the quoted term returns 1 (the phrase), the unquoted term 12 (separate words, including glucose-6-phosphate isomerase TcIL3000_0_29570).

**Why that's wrong.** The 12 is the word reading and is labelled the phrase, the reverse of what the line means to show, and the 987 reading was never a search term. One concept shows four counts and the reader cannot tell which one runs.

**Why it happens.** The alternative-reading measurement names an unquoted rewrite "phrase", and takes its second alternative from the constraint's requested value rather than the bound term.

**Fix.** The alternatives are derived from the bound term only: for a quoted term, "as separate words: N"; for an unquoted term, "as the phrase: N". The requirement's sentence is never a reading.

**What you'd get.** `as the phrase "GPI anchored": 1 gene; as separate words: 12`, and no "whose product is" row.
