---
type: Backlog
---

# An EDA export is impossible on the turn after the preview

**What I did.** On plasmodb, thread `eb4a2c63-f580-4058-96c2-7ae82bbd6170`. Turn 2 opened the heat-shock study, filtered to wild-type samples, previewed the groups (2 normal, 2 febrile) and ran the DESeq volcano: 5,442 genes tested, 1,564 passing, 569 up, 995 down, in a durable task that completed in 121 s. The reply said the summary carries totals but not the ranked table and offered the export as the next step. Turn 3 took the offer: "Export the genes that passed the volcano cutoffs into a strategy step so I can work with them, then tell me how many genes the step holds and show me five of their ids."

**What I got.** No export. The Lead reached for a search instead (`set_criterion(heatshock_volcano_export, GenesByRNASeqpfal3D7_Pfal3D7_Febrile_temps_RNASeq_ebi_rnaSeq_RSRCDESeq)`), which the tool refused ("eda_analysis_spec is written by the host, not proposed"), then `drop_criterion` failed on its own criterion id, and the reply was "I can't create the export step from the current workspace because the completed heat-shock differential analysis is not currently available to bind to a strategy ... Please reopen or complete the wild-type febrile-versus-normal analysis". 161 s, $0.09. The analysis is not lost: `conversation_analyses` holds the row (`DS_e973eadd57`, analysis `4XlEvvr`, revision 3).

**Why that's wrong.** The compute is the expensive part and it succeeded; the export is the cheap part and the researcher is told to run the compute again. The assistant also cannot say why, so it invents a reason ("not available to bind") and quotes a count (1,543) that disagrees with the one it reported last turn (1,564).

**Why it happens.** `ai/lead/intent_gate.py::unmet_preconditions` drops `create_eda_step` whenever `markers.eda_previewed` is false, and `TurnMarkers` is per message ("a turn answering a different message starts from an empty one"), so the preview from the previous turn cannot satisfy it. The tool is not refused with a reason: it is removed from the toolset, so the Lead cannot see it exists.

**Fix.** The precondition reads what the thread holds, not what this message did: `create_eda_step` is offered when the conversation has an open analysis whose subset was previewed (the analysis row plus a preview recorded on the analysis, not on the turn), and the preview marker stays a turn marker only for the "preview before you state a count" rule. A turn that exports without ever previewing anything still gets the refusal. Red first: a state whose stored analysis was previewed on an earlier message offers `create_eda_step`; a state with no analysis does not.

**What you'd get.** Turn 3 exports the 1,564 passing genes into a step, reports the step's count and five gene ids, and the strategy carries the cut.
