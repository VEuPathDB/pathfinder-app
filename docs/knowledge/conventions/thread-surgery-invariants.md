---
type: Convention
title: Thread surgery invariants
description: What a branch and a revert promise, one testable sentence each, with the test that fails when it stops holding. Covers the copied prefix, the model's visible history, the strategy revision and its WDK identity, the id space, repeatability, the EDA binding case by case, the library rows and cross-thread memory.
tags: [branching, revert, persistence, strategy-revision, testing]
generated: { by: claude-code/opus-5, at: 2026-08-31T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-31T00:00:00Z }
status: stable
---

Branch (fork) and revert are the two operations that move a thread sideways and
backwards. Both cut across data owned in four places: the log and the
checkpoints (`assistant_core` and LangGraph), the strategy and its revision
history, the thread's library references, and the EDA binding. Each sentence
below is one promise, and each names the test that goes red when the promise
stops holding. A change that makes one of these sentences false is a product
change, not a refactor.

The mechanism behind F3, R2 and the refusals is
[a strategy has a revision history](../decisions/a-strategy-has-a-revision-history.md).
The mechanism behind F7 and R7 is
[the thread log is the EDA binding's history](../decisions/the-thread-log-is-the-eda-bindings-history.md).

# Branch

| # | Invariant | Test |
|---|---|---|
| F1 | A branch holds exactly the messages at or before the anchor, in source order, and only the notes its own turns wrote. | `test_fork_case_matrix.py::test_f1_a_branch_copies_exactly_the_turns_at_or_before_the_anchor`, `...::test_f1_a_branch_copies_only_the_notes_written_by_its_own_turns`, `test_conversation_fork_and_delete.py::test_fork_messages_are_copied_in_order` |
| F2 | A turn run on the branch reads the history the anchor left: it sees every pre-anchor tool call and no post-anchor one. | `test_branch_model_history.py::test_f2_a_turn_on_a_branch_sees_the_anchor_s_history_and_no_more` |
| F3 | The branch's strategy is the anchor's snapshot pushed to WDK as a strategy of its own: a new strategy id and new step ids, even when later parent turns edited or cleared the tree. | `test_fork_materializes_revision.py::test_branch_at_turn_two_gets_the_three_step_tree_and_a_new_wdk_id`, `test_fork_case_matrix.py::test_f3_a_branch_owns_a_new_wdk_strategy_with_step_ids_of_its_own`, `test_materialize_snapshot.py::test_the_snapshot_is_pushed_with_no_wdk_ids_of_its_own` |
| F4 | A branch of a branch obeys F1 to F3 against its own parent, at any depth. | `test_fork_case_matrix.py::test_f4_a_branch_of_a_branch_obeys_f1_to_f3_against_its_own_parent`, `...::test_the_branch_tree_holds_f1_to_f4_together` |
| F5 | Every id in a branch is the branch's own: the message rows, the chunks' `messageId` and `message.id`, the `turn_id` column and the scratchpad note ids. Copied log rows carry `task_id = NULL`; `assistant_id` and `application_id` are the source's. The note copy is the runtime's `assistant_core.persistence.repositories.scratchpad.ScratchpadRepository.copy_notes_for_fork`, called from `services/conversations/fork.py`. | `test_fork_case_matrix.py::test_f5_every_id_in_a_branch_is_the_branch_s_own`, `test_fork_materializes_revision.py::test_a_branch_carries_no_parent_message_id_and_reverts_in_place`, `...::test_a_branch_of_a_site_help_thread_stays_site_help`, `test_fork_ids.py` |
| F6 | Branching is repeatable and read-only on its source: two branches of one anchor share no id and no WDK strategy, and every parent row is unchanged after a branch. | `test_fork_case_matrix.py::test_f6_two_branches_of_one_anchor_are_independent`, `...::test_f6_forking_leaves_every_parent_row_unchanged` |
| F7 | The branch opens the study its anchor had open, in a document of its own: the newest `data-eda.analysis-state` part in the copied log names the dataset, the display name and the filters, and the branch creates an analysis of its own from them. No such part means no study. A refusal from the study service leaves the branch unbound, never unforked. | `test_fork_case_matrix.py::test_f7_a_branch_opens_the_anchor_s_study_in_a_document_of_its_own`, `...::test_f7_a_branch_anchored_before_the_bind_opens_no_study`, `...::test_f7_a_study_service_refusal_leaves_the_branch_unbound` |
| F8 | The library rows stay the user's. A branch inherits the `experiment_id` it reads and never the `gene_set_id` it would rewrite: it starts unlinked and imports a gene set of its own on its first build. | `test_fork_case_matrix.py::test_f8_a_branch_owns_its_gene_set_and_keeps_reading_the_experiment` |
| F9 | Cross-thread memory is user-scoped, so a branch turn retrieves exactly what its parent's turn would. | `test_fork_case_matrix.py::test_f9_a_branch_turn_retrieves_the_memories_its_parent_would` |

A branch is refused rather than approximated in two cases, both pinned by
`test_fork_materializes_revision.py`: a thread with a strategy and no revision
history at all, and a thread with a durable task running in the copied prefix.

# Revert

| # | Invariant | Test |
|---|---|---|
| R1 | A revert deletes exactly the turns at and after the target: messages, log rows, notes, task rows, checkpoints, checkpoint writes and strategy snapshots. | `test_revert_case_matrix.py::test_r1_a_revert_deletes_exactly_the_turns_after_the_target`, `test_conversation_revert.py::TestRevertConversation` (per-table cuts, the `(created_at, id)` tiebreak, the checkpoint cut) |
| R2 | The strategy returns to the snapshot in force at the target, materialized: the tree is pushed to WDK again and the thread holds a strategy id and step ids of its own. It is cleared when no snapshot precedes the target, and a thread with no history at all is left alone. The route carries the registered-login gate that any WDK write carries. | `test_revert_restores_revision.py` (three cases), `test_revert_case_matrix.py::test_r1_a_revert_deletes_exactly_the_turns_after_the_target`, `test_revert_route.py::test_revert_without_a_veupathdb_login_is_refused`, `unit/transport/test_wdk_gate_route_table.py` |
| R3 | The next turn's model history is the history at the target: every pre-target tool call, no post-target one. | `test_branch_model_history.py::test_r3_a_turn_after_a_revert_sees_the_target_s_history_and_no_more` |
| R4 | Reverting to the same message twice ends where reverting once ended. The target row is one of the rows the first cut deletes, so the second call finds no such message and does nothing. | `test_revert_case_matrix.py::test_r4_reverting_twice_to_one_message_ends_where_once_did` |
| R5 | A revert inside a branch reads only that branch's own ids and times, at any depth, and leaves the surviving turns' chunks and notes in place. | `test_revert_case_matrix.py::test_r5_a_revert_inside_a_branch_of_a_branch_uses_that_branch_s_ids`, `...::test_r5_a_revert_inside_a_branch_keeps_the_surviving_turns_chunks`, `...::test_r5_a_revert_inside_a_branch_keeps_the_notes_of_surviving_turns` |
| R6 | A revert touches one thread. A sibling branch and the parent keep every row; a revert that deletes a branch point nulls that branch's back-reference and nothing else. | `test_revert_case_matrix.py::test_r6_reverting_one_branch_leaves_its_sibling_and_parent_alone`, `...::test_r6_reverting_the_parent_leaves_each_branch_s_content_alone` |
| R7 | The task rows the deleted turns created are gone, with their progress rows, and the EDA binding follows the surviving log. A thread whose log never recorded a binding is left alone. | `test_revert_case_matrix.py::test_r7_a_revert_past_the_bind_removes_the_tasks_and_the_binding`, `...::test_r7_a_binding_the_log_never_recorded_survives_the_revert`, `...::test_r7_a_revert_puts_the_recorded_filters_back_on_the_open_analysis`, `...::test_r7_a_revert_rebinds_the_analysis_the_deleted_turns_replaced`, `...::test_r7_a_revert_recreates_the_recorded_document_when_it_is_gone`, `...::test_r7_a_study_service_refusal_leaves_the_binding_where_it_was` |

## What R7 does, case by case

The newest surviving `data-eda.analysis-state` part is read after the cut, and
compared with the `conversation_analyses` row.

| The surviving log records | The row holds | What happens |
|---|---|---|
| no analysis-state part, and the thread's log never held one | anything | nothing: a study opened from the EDA tab alone emits no part, so no cut can claim it |
| no analysis-state part, where the log did hold one | nothing | nothing |
| no analysis-state part, where the log did hold one | an analysis | the row is deleted: the turn that opened the study is gone |
| an analysis, and the row names the same one | the same analysis | the recorded filters are read back from the service; when they differ from the live subset the subset is patched back and the revision grows by one, and when they agree nothing moves |
| an analysis the row does not name | another analysis, or nothing | the recorded analysis is patched to its recorded filters and bound, and the revision restarts at one. Replacing a binding never deletes the document it replaced, so the recorded id normally still resolves; a `404` from the service means the document is gone and one is created from the recorded descriptor instead |

A refusal from the study service in any of these leaves the binding exactly as
it was, with a logged warning. A revert is a thread operation, and a study
service nobody can reach must not cost the user the revert.

# Why the timestamps on a copy are load-bearing

A revert cuts on `created_at` (messages, notes, snapshots) and on `emitted_at`
(log rows). A branch therefore copies each row under its source's time, not
under the time of the copy. A copy stamped with the moment of the branch is
newer than every message it belongs to, so the first revert inside the branch
deletes it: the branch keeps its messages and loses the chunks that render
them.
