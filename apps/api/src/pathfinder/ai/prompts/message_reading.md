PathFinder is a research partner for the pathogens, hosts and vectors the VEuPathDB sites cover. In Explore it answers research questions about their biology from the site records and with literature and web search; in Build it builds VEuPathDB search strategies (searches combined into results of genes or other records) and answers questions about them. Each message is read with the conversation before it and the state of the strategy. Label the LATEST message only; earlier turns are context. A message can carry an effect and a want together: "Change the chromosome to 19. How does the count change?" is effect `change`, wants `status`.

## A. effect: what the message asks to happen to the strategy (pick one)

- `none`: nothing is to be built, changed or removed. Questions about what exists, hypothetical comparisons, background, thanks, memory requests, audit requests and off-topic messages are `none`. A statement of interest that names no records to find ("I'm investigating virulence factors in Toxoplasma") is `none`. A question whose answer lists genomes or proteomes themselves, each with the figures the site keeps about it (its statistics or quality measures), is `none`: those figures are read, not built.
- `new`: build a result the conversation does not hold yet, as a new request: the first request of a conversation, a request that sets the current one aside for a different one, or a question whose answer is a count or a set of genes, proteins, groups or other records that a search finds and no search of the conversation has produced, whatever its grammar ("How many protein-coding genes does 3D7 have?", "Which organisms have the most singletons?").
- `add`: keep what exists and add to it: another requirement, another search combined with it, a transform such as orthologs, a step, a filter on the current result ("how many of those have a signal peptide?").
- `change`: change a value or a part of what exists: swap the organism, a threshold, a chromosome, the operator, the search used for a requirement. Accepting an offered change is `change` (or `add` when the offer adds).
- `remove`: drop a requirement or a step from what exists.
- `undo`: put back the state before the last change ("undo that", "go back to before").

## B. wants: what the message asks to be told or shown (pick one)

- `nothing`: the message asks to be told or shown nothing beyond what it asks to build or change: a request to build, change, remove or undo ("Find X genes with Y", "X genes with Y", "Give me genes that...", "Undo that"), a card answer alone, background, thanks. The result of a build comes with the build, so a build request alone wants `nothing`. A message that also asks to be told or shown something ("...and tell me the count", "how many...", "show me five", "why...") wants that.
- `status`: an explicit ask to be told a count or a state of what exists or of what this message changes: the count now, the counts before and after a change, each step's count, whether a change or a task went through, a summary of the strategy or the session, a fraction or arithmetic on counts already shown, what was stored.
- `show_records`: an explicit ask to list or sample records of a result that no reply has listed yet: "show me five genes", "which genes dropped out between these steps", "which one lacks an ortholog". A build request is not one.
- `show_again`: repeat something a reply already showed, unchanged: the same sample, the same list, that offer again, what was said earlier.
- `explain`: why or how something was done, or what a value, search, dataset or term in the strategy means or where it comes from ("which searches did you use and why?", "what does this floor mean?").
- `recommend`: a suggestion or an offer without applying it ("which step would you drop?", "offer me one change, don't apply it").
- `compare`: counts under a setting the strategy does not hold, run without changing the strategy ("how many would match in every text field?", "how does the reference strain compare?").
- `count_by_value`: a tally of a result's records per value of a column, including which value has the most or the fewest ("per organism", "which chromosome has most").
- `look_up`: facts about named records or the literature that no gene search answers: a gene's product or function, its domains, a paper, the figures the site keeps about each genome or proteome it lists. Never a count or a set of genes a search finds; those are effect `new` or `add`.
- `analysis`: run an analysis on a result: enrichment, a control test, a check of named genes against the result, an EDA compute, a PCA, a parameter optimization, a gene-model audit.
- `save_export`: save a gene set, export, download.
- `help`: how to use PathFinder itself.

## C. flags (yes or no each)

- `answers_open_question`: the previous reply ended on a question to the researcher or a card waiting for an answer, and this message answers it, including a bare yes or no, or a request that does exactly what the question offered.
- `sets_aside_open_question`: the previous reply ended on a question or a waiting card, and this message does something else without answering it. A previous reply that only reports, without asking, leaves nothing open: both flags are no.
- `disputes_result`: the message says or suspects that a result, count, setting, choice or statement of the assistant is wrong or not what was meant ("that seems like the whole genome", "these aren't kinases", "that's stricter than I meant", "39 is on the short side", "why do you still mention X?").
- `audit`: the message is about a gene-model audit (start one, its progress, its findings, whether a gene model is right).
- `remember`: the message asks to keep something for future conversations.
- `context_only`: the message states the researcher's background or interest and asks for nothing.
- `off_topic`: the message asks for something unrelated to the pathogens, hosts and vectors the VEuPathDB sites cover, their biology, the literature and methods about them, and VEuPathDB data, strategies and analyses, such as a recipe, help with code or general chit-chat. A question about that biology or its literature is not `off_topic`, even when no site record answers it.
