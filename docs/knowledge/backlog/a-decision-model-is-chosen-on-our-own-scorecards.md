---
type: Backlog
title: A decision model is chosen on our own scorecards
description: Cloudflare's open-weight Clef and Clef-flash answer the same typed questions as TypeSafe's Jev; the Jev scorecards are rerun on both before any decision model is wired into PathFinder.
tags: [models, decision-models, injection, verify, catalog]
generated: { by: claude-code/opus-5, at: 2026-10-04T00:00:00Z }
status: proposed
---

# A decision model is chosen on our own scorecards

**Parked.** Nothing here is wired. A decision model answers typed questions
(yes or no, one of a list, a point on a scale) with a probability for each
answer. Two exist: TypeSafe's Jev (`typesafe/jev-1.13`, reached through
OpenRouter's `POST /api/alpha/decisions`), and Cloudflare's Clef (27B, on
Qwen3.8-27B) and Clef-flash (9B, on Qwen3.5-9B). Cloudflare released both on
2026-10-01 under Apache 2.0, with weights on Hugging Face (`Cloudflare/clef`,
`Cloudflare/clef-flash`) and hosted on Workers AI (`@cf/cloudflare/clef`,
`@cf/cloudflare/clef-flash`). Clef takes the Jev request shape (`state`, and
`questions` of type `noul`, `choice` or `score`), reads 64k tokens against
Jev's 32k, and reads images.

## What is known

Jev was measured on five PathFinder uses. None shipped. In rank order:

1. A second injection screen on tool results. The injection judge on Luna
   caught 108 of 117 attacks; the judge OR Jev at confidence 0.85 or more
   caught 117 of 117, with no false alarm on 174 clean results.
2. VERIFY's per-record fit: Jev 297 of 367 right, Luna 275.
3. Candidate searches over the whole catalog, beside `search_for_searches` in
   veupathdb-mcp: Jev's choice over every search held the right search in
   1,195 of 1,394 cases, more than the embedding shortlist.
4. A flag on obsolete or no-fit vocabulary values.
5. A disagreement flag beside the intent gate.

Cloudflare's own numbers put Clef ahead of Jev on classification and tool
choice (BANKING77 macro-F1 94.20 against 79.74) and behind on judgment
(When2Call 72.37 against 80.97, agent trace review 68.5 against 71.6).
Clef-flash detects out-of-scope input at 66.77 against Jev's 89.27. Cloudflare
chose and ran these evaluations, the public Decision Index has not reproduced
them, and no calibration is published. Hosted prices per million input tokens:
Clef $0.24, Clef-flash $0.09, Jev $0.042.

## What remains

- A Cloudflare account ID and a Workers AI API token, or proof that
  OpenRouter's decisions endpoint serves Clef. Its public model list names
  neither Clef nor `jev-1.13`.
- Rerun the five scorecards on Clef and Clef-flash, changing only the model
  and the endpoint. The Jev run cost about $2, so expect about $12 and $5.
- Compare each use on the same items. The injection screen and VERIFY fit are
  judgments, where Jev leads on the vendor's numbers. Candidate finding is a
  choice among many options, where the larger context halves the chunks per
  catalog. The vocabulary flag depends on out-of-scope detection.
- Self-hosting needs a GPU. The 27B model was tested on one H200 and cedar has
  no GPU, so the hosted models are measured first.
