---
type: Decision
title: A parent term is a selection, so the tree expands it
description: The organism tree matched only leaves, so a step correctly scoped to "Plasmodium falciparum" opened reading "0 of 62 selected" on a required field.
tags: [frontend, parameters, wdk-alignment, data-integrity]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# The trap

Found on a real account. A one-step strategy returning 11,798 transcripts stored:

```json
"organism": { "type": "multi-pick-vocabulary", "values": ["Plasmodium falciparum"] }
```

Opening that step showed **ORGANISM \*** (required) reading **"0 of 62 selected"**, nothing checked. The strategy was correct; only its rendering was wrong.

Confirmed against live WDK: `"Plasmodium falciparum"` is a vocabulary node at depth 3 with **20 children** (3D7, 7G8, CD01, Dd2, ...). It is a parent, not a leaf, and `TreeBoxParam` matched leaves only.

# Why the value is a parent in the first place

That is the backend's design, not a mistake. `_prepare_search_config` calls `_expand_tree_params_to_leaves` before pushing, precisely because *WDK silently returns 0 genes for a parent node*. So a parent term is a legitimate stored value that is expanded at the WDK boundary. The UI simply never learned the same rule.

# Why it was worse than cosmetic

A required field that looks empty invites the researcher to fill it. Worse, the edit handlers filtered the **raw** stored value: unchecking one leaf while `["Plasmodium falciparum"]` was stored removed nothing, so the whole branch silently stayed selected. Display and mutation disagreed with the truth in different directions.

# The fix

`expandToLeaves(values, tree)` maps any parent term to the leaves beneath it. Selection state, the count, and both edit handlers now work from that expanded view, so what the tree shows is what will be queried, and an edit starts from what the user can see. Unknown values pass through untouched rather than vanishing.

The alternative -- teaching the tree to render a parent as its own selection -- was rejected: it would keep two representations of one parameter, which is what caused this.

# Anchor

`expandToLeaves` in `features/strategy/editor/widgets/TreeBoxParam.tsx`, against `_expand_tree_params_to_leaves` in `veupathdb/wdk/strategy_api/steps.py`. Guarded by "a value stored as a parent term" in `TreeBoxParam.multiPick.test.tsx`, including the two mutation cases.
