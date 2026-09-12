---
type: Backlog
---

# Consult answers can be dropped between the carousel and the turn

**What I did.** On cryptodb, thread `53fc506d-308e-44b7-bdbe-66e75e074d3e`, twice: a message that forces `consult_user` to ask two single-choice questions, then the carousel answered by picking an option on each slide and pressing Next, then Submit.

**What I got.** The first time: the resumed turn's `consult_user` returned `output: []`, and the reply printed "Q: Which infectious stage should define expression ... A: -" for both questions and asked them again, ending the turn with nothing built ($0.007, 147 s). The second time, the same flow through the same driver: the request body carried the part (`data-user-question-answers`, toolCallId `call_F3dYyP5Q56dPNkM84waWqr38`, both answers with their chosen labels) on the assistant message, and the turn applied them (dropped a criterion, rebound the expression search).

**Why that's wrong.** The researcher answered two questions and was told they answered nothing, then asked the same two questions. Nothing in the thread says the answers were lost, so the natural reading is that the assistant ignored them.

**Why it happens.** `apps/web/src/features/conversation/rail/consultActions.ts::handleConsultSubmit` writes the answers into the message list (`chat.setMessages`, matching `msg.id === pending.sourceMessage.id`) and then calls `chat.addToolApprovalResponse` in the same tick. The answers reach the server only if that state update is applied to the list the transport reads when it builds the body (`runtime/buildRequestBody.ts` takes `messages` as given), and only if a message with that id is still in the list; the map is a silent no-op otherwise. The server side is honest about the absence: `ai/conversation/_turn_helpers.py::_extract_user_question_answers` finds no part, and `ai/lead/lead_consult.py` reads `state.user_question_answers.get(tool_call_id, [])`.

**Fix.** The answers stop riding the message list: `handleConsultSubmit` records them in the chat runtime's own keyed store (approvalId to answers) that `buildChatRequestBody` reads and puts on the body, so the send carries them whatever React has flushed and whatever the message ids are. A submit whose approval id is unknown to the store fails loudly instead of sending an empty answer set. Red first, in jsdom: submitting the carousel and immediately triggering the request build produces a body carrying both answers; a submit for an approval id the runtime does not know throws.

**What you'd get.** Every carousel submit reaches the turn, and the questions are never asked twice.
