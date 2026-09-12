---
type: Backlog
---

# The cross-organism refusal prescribes the wrong remedy after a transform

**What I did.** On plasmodb in the debugger, the precise candidate-drug-target gold prompt: four kinase searches across all Plasmodium, "Combine all and transform to P. falciparum 3D7 non-syntenic orthologs", then mass-spec or DeRisi-expression evidence in trophozoites, low SNP density, and a Plasmodium-specific phyletic profile. Run `apps/api/.pf-runs/drive/t2/d3/turn1`, conversation `b52e052a-4a19-47d2-97e9-d5c4d4fe0797`.

**What I got.** FRAME set the transform (`GenesByOrthologs` to P. falciparum 3D7) as the root over everything else, so the P. falciparum 3D7 filters were intersected with the all-Plasmodium kinase union underneath it. The build's validator refused the combine: "Cannot INTERSECT steps with different organism scopes (Plasmodium falciparum 3D7 vs Plasmodium). Gene IDs from different species never match, so this always returns 0 results. Apply organism-specific filters BEFORE any ortholog transform, not after." The recovery pass kept that shape, 16 WDK steps were pushed with no readable size, no strategy row was written, and the reply reported the refusal as "an incompatible cross-organism intersection". $0.37, 846K tokens. The gold (WDK 330152163, 19 genes) is the shape the message forbids: union, then the transform, then the P. falciparum 3D7 filters after it.

**Why that's wrong.** The refusal is right about the shape it saw and wrong about the cure: a filter scoped to the transform's target organism belongs after the transform, and the one remedy the message names moves it further from the answer. A precise 16-step request ended with no strategy and sixteen orphaned steps.

**Why it happens.** `domain/strategy/validate.py::_validate_cross_organism_intersect` writes one fixed remedy into every refusal, whichever side of the transform the disjoint scopes came from; `extract_output_organisms` (veupathdb-py) already knows the transform's target, so the validator can tell which remedy applies.

**Fix.** The refusal names the two scopes and the remedy that matches them: when the strategy holds a transform whose target organism equals one side of the disjoint pair, "move the <target> filters after the <transform> transform"; otherwise "scope the seeds to <organism>". FRAME's structure guidance says the same in one sentence: a criterion scoped to the transform's target organism sits above the transform. Red first with the run's structure (all-Plasmodium seeds, a transform to P. falciparum 3D7 at the root, P. falciparum 3D7 filters below it): the refusal names the move-after remedy and the transform.

**What you'd get.** The recovery pass moves the three P. falciparum 3D7 filters above the transform and the strategy builds (the gold answers 19).
