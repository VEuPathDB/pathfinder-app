---
type: Backlog
---

# A step the editor deleted cannot be added back by the assistant

**What I did.** On plasmodb, thread `4fb5057b-f36e-417d-ab10-e714f9694888` held a three-step strategy (WDK 214618650: signal peptide 463 INTERSECT at least one transmembrane domain 1,305 = 195, P. berghei ANKA). In the graph editor I chose "Delete and collapse" on the transmembrane step; WDK went to one step (463) within seconds. Then I sent: "I deleted the transmembrane step in the editor by mistake. Add it back exactly as it was (at least one predicted transmembrane domain, same organism) and intersect it with the signal peptide step again. What is the count now, and does it match what we had before?"

**What I got.** Intent `edit_strategy`, FRAME `set_criterion(step_2ea81607 -> GenesByTransmembraneDomains)` and `set_structure` ("2 criteria"), then `get_strategy` "1 steps, 463 genes", the same two framing calls again, and the reply "I couldn't complete the restoration because the transmembrane step and its intersection are no longer present in the live strategy". No build was dispatched. The ledger's frame diff reads `kept` for both `step_3fa0e628` and `step_2ea81607`, addedCount 0, structureChanged false, while `build.staleBuild.removedNodes` is `["step_2ea81607", "step_3c07753b"]`. WDK still holds one step. 102 s, $0.03.

**Why that's wrong.** The editor and the assistant are two hands on one strategy. A step removed by one hand and asked back by the other is the most ordinary recovery there is, and the assistant answers that the step it is being asked to add is missing.

**Why it happens.** `ai/lead/pre_turn.py::_hydrate_spec_from_the_strategy` returns as soon as the checkpoint carries a spec with criteria, so after an editor delete the turn starts from the spec the earlier build framed (two criteria, `step_2ea81607` among them). `spec_before_turn` is a copy of that spec, `ai/lead/edit_dispatch.py::run_edit` diffs FRAME's spec against it, the criterion reads as `kept`, `operations_for` yields nothing, and the turn ends with "The strategy already states everything the edit asks for" while the graph lacks the step. The staleness the same pre-turn measured (`removed_nodes`) never reaches the spec.

**Fix.** The pre-turn reconciles the framed spec with the live graph before recording the entry spec: a criterion whose step is not in the graph leaves `operational_spec` (its leaf leaves the structure, a combine with one input collapses), so `spec_before_turn` states what the strategy states. Then FRAME binds the transmembrane criterion as new, the diff says `added`, and the push creates the step and the combine. `domain/strategy/staleness.py` already names the removed nodes; the reconciliation is a domain function beside it (`spec` x `graph` -> `spec`), applied in `refresh_live_strategy_state` after staleness. Red first: a state whose checkpoint spec holds two criteria and whose graph holds one step enters the turn with a one-criterion spec, and an edit that frames the second criterion diffs as `added`.

**What you'd get.** The reply: the step is back, 1,305 genes, intersection 195, the same as before.
