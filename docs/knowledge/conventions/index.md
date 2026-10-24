# Conventions

- [Maintaining this bundle](maintaining-this-bundle.md) - what belongs here, and the rule that stops it rotting
- [Verification gates](verification-gates.md) - the commands that decide whether work is done
- [Thread surgery invariants](thread-surgery-invariants.md) - what a branch and a revert promise, one testable sentence each, with the test that fails when it stops holding
- [The eval curation rubric](eval-curation-rubric.md) - what a staged candidate must satisfy to be promoted; privacy hard rules, quality rules, weekly cadence
- [One name per concept](vocabulary.md) - the lexicon `scripts/check-vocabulary.mjs` reads: each concept's name, the synonyms it bans and where, the exemptions, and the pairs that are two concepts
- [Refreshing the model catalog](refreshing-the-model-catalog.md) - the one module that names a model id, the tiers its ranks derive, and the check that compares it with what each provider serves
- [Observability](observability.md) - what a turn's trace holds, the attribute names Langfuse maps, which view answers which question, and the usage devtool
- [Recording the audit models](recording-the-audit-models.md) - how the intron-check results the audit fact tests read are written again from the library's recorded wires, with no site request
