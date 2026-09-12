---
type: Backlog
---

# A transform criterion binds a search that takes no input

**What I did.** On plasmodb, the precise protease gold prompt: proteases by text OR GO term (curated and computed), filtered by top 20% gametocyte expression (Su strand-specific), transformed to P. vivax P01 non-syntenic orthologs, then intersected with the non-synonymous SNP search (80% read frequency, 70% isolate call rate). Run `apps/api/.pf-runs/drive/t2/d1/turn1`.

**What I got.** FRAME asked `get_search_overview(search_name="GenesByOrthologs")` and was refused ("not a known value ... Choose one of: GenesByEcNumber, ... GenesByNgsSnps, ..."; the transform is not in that vocabulary), then bound the criterion `vivax_orthologs` with role `transform` to `GenesByOrthologPattern`, the phyletic-profile leaf search. The build created "transform step input=227253120 transform=GenesByOrthologPattern", and the strategy POST answered `422: Step 227253130 does not allow a primary input step.` three times (once per BUILD recovery attempt). No strategy, 52 calls, $0.27; the reply says "the orthology-transform step cannot be used as a primary input in that combination", which names the symptom and not the cause. The same shape built this morning in 58 calls (133 genes) when FRAME found `GenesByOrthologs` through `list_transforms`.

**Why that's wrong.** A researcher who states the transform by name gets no strategy and an explanation that blames the graph shape; the three pushes each left a step in the account.

**Why it happens.** `set_criterion` (`ai/tools/standalone/frame_spec.py`) accepts `role="transform"` for any search the catalog names, and the push (`services/strategies/step_wdk_push.py`, the transform branch) hands the criterion's input to a search that declares no `allowedPrimaryInputRecordClassNames`; nothing compares the role with what the search accepts. And `get_search_overview`'s vocabulary is the site's leaf searches, so a transform's name is refused there while `list_transforms` is the only tool that carries it, which the sheet does not say.

**Fix.** `set_criterion` with `role="transform"` refuses a search that accepts no primary input, naming the transforms the site offers for the record type (the catalog already knows `allowedPrimaryInputRecordClassNames`), and `get_search_overview` answers a transform's name with its overview instead of a vocabulary refusal (or its refusal names `list_transforms`). Red first with the measured call: `set_criterion(criterion_id="vivax_orthologs", role="transform", search_name="GenesByOrthologPattern")` is refused with `GenesByOrthologs` named; the push never receives a transform criterion on a leaf search.

**What you'd get.** FRAME binds the P. vivax orthologs transform on the first pass, the strategy builds (the gold answers 257 with the Su strand-specific dataset), and no step is left behind by a push that could not succeed.
