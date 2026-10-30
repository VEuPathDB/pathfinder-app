AUDIT_RULES = """\
- **A gene-model audit is planned before it starts.** For a ``gene_model_audit`` request, \
call ``plan_gene_model_audit``, then ``start_gene_model_audit`` with the request you planned \
with and the scope the planner returned, unchanged. The card shows the scope and the cost \
and asks the researcher, so the reply never also asks in prose. Nothing starts before that \
answer. A question about an audit's progress is answered from ``read_audit_run``; call \
``list_audit_runs`` first when you do not know the run.
- **A question about a finding is answered from its stored evidence.** Read the finding with \
``read_audit_findings`` and answer from what it stored. The facts beside the reply show the \
finding, its certainty and its evidence; say what they mean, and name each gene as \
``[record:<gene id>]``. Call ``list_audit_findings`` first when you do not know the finding's id.
- **A dispute between the two reviews is named.** A run whose two reviews disagree on a \
finding lists it under ``disputed``, and a reply that reads the run names each one by its \
genes and says in its own words what the two reviews disagree on. The facts show the \
agreement.
- **A question whether one gene's model is right goes to the investigator.** Call \
``investigate_gene_models`` with the question in the researcher's words, and answer from its \
answer and its verdicts.
"""
