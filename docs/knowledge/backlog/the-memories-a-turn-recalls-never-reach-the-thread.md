---
type: Backlog
---

# The memories a turn recalls never reach the thread

**What I did.** Counted the chunks of type `data-memory-retrieved` in `conversation_events` across the whole database (highest event id 239587), then ran the turn-entry retrieval by hand in the api container for the user of thread `4fb5057b-f36e-417d-ab10-e714f9694888` with that thread's request ("Find genes with a predicted signal peptide and at least one transmembrane domain. Give me the count."), under the `pathfinder` application context, with the same arguments `ai/graph/_lead_turn.py::retrieve_memories` passes.

**What I got.** Zero chunks, ever, on any thread. The retrieval by hand returns 8 memories (a strategy memory at 0.853, four cases from 0.841 down, three more strategies), so the store answers and the Lead does read them as pinned memories. The thread shows nothing of it: no recalled-memories row, and the Memory settings' "used in this turn" view has nothing to draw.

**Why that's wrong.** A researcher cannot see which earlier work shaped a turn, and neither can anyone debugging a turn that cited a stale count from memory; the thread claims no memory was used while eight were.

**Why it happens.** `ai/graph/lead_node.py::_run_lead_turn` hands the chunk to the stream writer bare (`writer(memory_retrieved_event(memories=stored))`) while every other emission goes through `emit_chunk`, which wraps it as the `{"chunk": {...}}` envelope; `ai/conversation/_turn_helpers.py::_extract_chunk` returns `None` for anything that is not that envelope, so the turn runner drops the payload before the event writer sees it.

**Fix.** `emit_chunk(writer, memory_retrieved_event(memories=stored))`. Red first: a unit turn over a mock Lead with one stored memory asserts the writer received the `data-memory-retrieved` envelope, through the same `_extract_chunk` the runner uses; a second assertion in the existing lead-node stream test forbids a bare `writer(` call in `ai/graph` (the envelope is the only shape the runner reads).

**What you'd get.** The thread's recalled-memories row lists the eight memories with their scores, on every turn that retrieved any.
