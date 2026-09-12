---
type: Backlog
---

# The Lead classifies a message the user never sent

**What I did.** On toxodb, one message: "Find Toxoplasma gondii ME49 genes with a signal peptide or a transmembrane domain, whose cell-cycle microarray expression profile is similar to both MIC2 (TGME49_201780) and RON2 (TGME49_300100), and whose orthologs are present across Apicomplexa but absent from mammals. Give me the count and a few examples." FRAME bound five criteria (720, 1,742, 50, 50, 44) and the spec build read 0 at the root.

**What I got.** The Lead's first `final_result` was the right answer ("The strategy returned **0 genes** ... One concrete way to broaden the result is to relax the profile-similarity cutoff ...", `nextState: await_user`), and no BUILD recovery was dispatched. Because the turn had built and never verified, `verify_what_this_turn_built` refused that reply once. The Lead's next call was `classify_user_intent(rawText="Fix the errors and try again.", classification="new_strategy")`: a message nobody sent. It then re-read the ledger, called `consult_user` ("How should I broaden the two cell-cycle profile searches ...", recommended "Return the top 100 genes"), the harness answered the consult, two more FRAME passes were dispatched to "honor the user's hard clarification" of top 100, and the reply the user finally received says "I couldn't safely apply the requested top-100 correction ... your top-100 instruction", attributing to the user an instruction the Lead wrote for itself. 33 tool calls, $0.07.

**Why that's wrong.** The thread now holds a user_explicit hard constraint ("Return the top 100 genes for each profile", `source: user_explicit`) the user never stated; every later turn carries it as the user's word, and the reply blames the user for a change the assistant invented. The honest zero the turn had already written was replaced by a paragraph about a correction nobody asked for.

**Why it happens.** `classify_user_intent` (`ai/lead/lead_tools.py`) takes the message text as a model-supplied argument, so the Lead can classify any text it composes and the classification lands in the ledger as the user's intent; and the verification validator's retry is answered by the model with whatever it likes, since nothing binds the retry to the one tool it asks for.

**Fix.** The intent gate classifies the turn's own user message: the tool takes no text argument and reads the message from the turn state, so a classification of an invented message is impossible. The validator's retry names `verify_strategy` and the precondition gate offers only that tool until it is called (the gate already narrows the list by turn phase). Red first: `classify_user_intent` has no text parameter; a Lead run whose first reply follows an unverified build has `verify_strategy` as the only building tool after the refusal.

**What you'd get.** The first reply (0 genes, with the broadening offered) is verified and delivered; no constraint the user did not state enters the thread.
