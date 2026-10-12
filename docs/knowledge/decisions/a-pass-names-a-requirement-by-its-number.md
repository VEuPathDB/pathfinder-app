---
type: Decision
title: A pass names a requirement by its number and is corrected inside its own run
description: FRAME reads the researcher's requirements as a numbered list and reports a requirement the strategy does not answer as asked by its number with one of four problems, so the words of a report are the words the thread holds and no check compares FRAME's prose to a message. A report with a number the list lacks, and a question that binds nothing, go back to FRAME once inside its own run. Free text held to the researcher's words by a word match, a rewording of that refusal, a notes field, a field for a requirement the list lacks, and a refusal sent to the Lead were rejected.
tags: [agents, frame, lead, requirements]
generated: { by: claude-code/opus-5.5, at: 2026-10-12T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-10-12T00:00:00Z }
status: stable
---

# What was decided

**A report is a number and a problem.** FRAME's instructions pin
"Requirements the researcher stated" (`ai/agents/strategy_instructions.py::pinned_requirements`),
each requirement the thread holds with source `user_explicit`, numbered in the
order held (`domain/strategy/requirement_reports.py::numbered_requirements`).
`FrameResult.requirement_problems` holds one `RequirementReport` per requirement
the strategy does not answer as asked: the number, and a `RequirementProblem`:

- `site_has_no_search`: no search on the site can answer it and nothing is bound.
  The dispatch resolves it to the held requirement, the facts part shows it as a
  gap in the held words, and the card offers to drop or keep it. An organism or a
  record type is a scope every search runs in and is never offered for withdrawal.
- `stand_in_bound`: the nearest search is bound in its place.
- `needs_the_analysis_workflow`: only the Lead's analysis tools write it.
- `request_leaves_it_open`: the request gives no value a parameter needs, and the
  pass asks for it.

The Lead never reads a number. The dispatch sets `reported` on the `FrameResult`
and the `EditDelta`: each report as a `ReportedRequirement` with the held words,
the problem and `what_to_do`, the sentence that says what the Lead does about it.

**A correction reaches the pass that made the mistake.** FRAME's agent has two
output validators (`ai/agents/frame_result_checks.py`). A report whose number the
list lacks is sent back once with the numbers the list holds; after that the
dispatch drops it. A pass that stops on the user with a question that binds
nothing (`ai/lead/frame_questions.py::questions_that_bind_to_nothing`) is sent
back once with the slots its draft holds. FRAME keeps its history, its draft and
its tools, so the correction costs one request and the pass records the
criterion or reports the requirement. When a pass still ends on such a question,
the dispatch returns each criterion it found to the values it was found with, so
the plan moves no built step before an answer, and the Lead reads the question.

# What was rejected

**Free text held to the researcher's words by a word match.** The field held
FRAME's sentences, and the check passed an entry when a message carried each of
its words. It refused sentences that reported a true limit of the site and
accepted fragments and questions copied from a message. In 595 saved FRAME
results, 141 wrote an entry and 111 of those failed the check. A refusal went to
the Lead, which dispatched a new pass of 200,000 to 400,000 tokens that wrote
another sentence.

**A rewording of the refusal.** The field description and the refusal already
said a note is no requirement. A replay of the saved requests under that wording
was refused again in 58 of 115 answers.

**A notes field beside the list.** A replay with and without it gave the same
reports, and with it the pass wrote a note in more than four of five answers
that had nothing to report. `summary` carries what else the pass has to say.

**A field for a requirement the list lacks.** A replay that offered one, with the
researcher's exact words, saw it used in none of 95 answers. A requirement the
classification missed is said in `summary` and shows no gap row.

**A refusal sent to the Lead.** The Lead did not write the result and can only
dispatch again. A replay of 47 saved passes that asked about a criterion their
draft lacked repeated the question in 28 of 37 answers under any result shape,
and in none of 28 after one correction inside the run.

# Anchors

`domain/strategy/requirement_reports.py`, `ai/agents/frame_result_checks.py`,
`ai/agents/strategy_instructions.py::pinned_requirements`, `ai/agents/frame.py`,
`ai/lead/deltas.py::FrameResult`, `ai/lead/frame_requirements.py`,
`ai/lead/frame_dispatch.py::run_frame`, `ai/lead/frame_questions.py`,
`ai/lead/edit_dispatch.py::run_edit`,
`tests/unit/domain/strategy/test_a_requirement_report_names_a_held_requirement.py`,
`tests/unit/ai/agents/test_frame_is_told_inside_its_own_run.py`,
`tests/unit/ai/agents/test_a_frame_question_is_sent_back_inside_the_pass.py`.
