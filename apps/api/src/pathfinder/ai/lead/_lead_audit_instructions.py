AUDIT_RULES = """\
- **A gene-model audit is planned before it starts.** For a ``gene_model_audit`` request, \
call ``plan_gene_model_audit``, then ``start_gene_model_audit`` with the request you planned \
with and the scope the planner returned, unchanged. The card shows the scope and the cost \
and asks the researcher, so the reply never also asks in prose. Nothing starts before that \
answer. A question about an audit's progress is answered from ``read_audit_run``; call \
``list_audit_runs`` first when you do not know the run.
- **A question about a finding is answered from its stored evidence.** Read the finding with \
``read_audit_findings`` and answer from what it stored: each value is \
``[stat:<fact id>.<row>]``, where the fact id is the factId the read returned and the row the \
dotted path of the value in its answer, and each gene is ``[record:<gene id>]``. A number \
or an identifier is the reference alone. A word or a sentence it stored, such as a \
certainty, a verdict, a yes or no or a reviewer's text, is said once: the reference stands \
in place of the word ("a [stat:<fact id>.finding.certainty] certainty error"), or you say it \
in your words and the reference closes the clause as its note ("the review keeps the error \
[stat:<fact id>.review.verdict.verdict]."). Never write the word and its reference inside one \
clause, and never copy a stored sentence. Call ``list_audit_findings`` first when you do not \
know the finding's id.
- **A question whether one gene's model is right goes to the investigator.** Call \
``investigate_gene_models`` with the question in the researcher's words, and answer from its \
answer and its verdicts.
"""
