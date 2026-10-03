---
type: Backlog
title: A lookup ranks the request's own words first
description: A vocabulary lookup whose matches exceed the list shown to the pass shows them in the order the phrasings matched, so entries that carry the request's own words can fall below entries matched by a synonym the pass wrote; the library's read_options ranks phrase matches of the request's words ahead of the pass's phrasings.
tags: [frame, lookup, library]
generated: { by: claude-code/opus-5, at: 2026-10-03T00:00:00Z }
status: proposed
---

# A lookup ranks the request's own words first

**What I did.** On vectorbase, "Aedes aegypti LVP_AGWG odorant-binding protein genes on chromosome 3"; the pass read the domain vocabulary with the phrasings 'odorant-binding protein', 'pheromone binding' and 'insect pheromone-binding'.

**What I got.** 390 entries matched and the list shown to the pass was cut; the facts row read "took 1 of the 390 entries that match ...; the list it was picked from showed only part of them". The entry the pass took, PF03392 "Insect pheromone-binding family, A10/OS-D" (43 genes, 8 on chromosome 3), was matched by the pass's own synonym, while IPR006170 "Pheromone/general odorant binding protein domain" carries the request's words.

**Why that's wrong.** The pick rule now refuses an entry whose label shares no uncommon word with the request, so the pass is sent back to the list; a list that hides the entries carrying the request's words makes the retry a guess.

**Why it happens.** `veupathdb_mcp.catalog.vocab_lookup.read_options` ranks phrase matches first within each phrasing, in the order the phrasings were given; a synonym the pass wrote ranks beside the request's own words, and the cap cuts the list before the request's entries.

**Fix.** In the library, `read_options` takes the request's own concept words beside the phrasings and ranks entries that carry them first, phrase matches before word matches; the capped list says how many of the request's own entries it holds. A library release and a pin bump follow.

**What you'd get.** IPR006170 and PF01395 at the top of the list for that request, and a pass that binds one of them on the first try.
