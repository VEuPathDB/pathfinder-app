---
type: Backlog
---

# A new goal is not honored while a question with no dimension stands

**What I did.** On plasmodb, turn 1 asked for "P. vivax genes ... combine text and GO evidence for proteases", which states `{kind: organism, "Plasmodium vivax"}` and `{kind: combination, "text evidence OR GO evidence"}`. FRAME stopped on the user and its questions were recorded, as `FrameResult.open_questions` carries them: bare strings, so each is stored with the default dimension `other`. Turn 2 was "Forget that. Find P. falciparum kinases.", classified `new_strategy` and stating `{kind: organism, "Plasmodium falciparum"}`. Measured twice: with one dimensioned question beside one bare one, and with only bare questions.

**What I got.** The abandoned requirements stay:

```
J new goal, named + bare question -> ['Plasmodium falciparum', 'Plasmodium vivax', 'text evidence OR GO evidence']
J frame combination reqs -> ['text evidence OR GO evidence'] | organism hints -> ['Plasmodium vivax', 'Plasmodium falciparum']
K new goal, only bare questions -> ['Plasmodium falciparum', 'Plasmodium vivax', 'text evidence OR GO evidence']
```

**Why that's wrong.** The kinase strategy the user asked for is still gated on the protease union: `first_combination_violation` refuses with a `ModelRetry` any tree that does not join those criteria at UNION, and both organisms reach FRAME as hints. The user said "forget that" and the abandoned request still shapes the tree and the searches.

**Why it happens.** `FrameResult.open_questions` (`ai/lead/deltas.py`) is `list[str]`, so `StrategyDomainState.record_questions` stores every one of them with `dimension` at its default `other`. `continues_the_request` (`ai/graph/state.py`) cannot read a default as a statement about the answer, so a set holding any such question keeps the requirements whatever the message says.

**Fix.** Give a sub-agent's question the dimension its open slot already decides: `FrameResult.open_questions` carries `OpenQuestion` (the domain type it is recorded as) instead of bare strings. Then no recorded question is dimensionless, `continues_the_request` matches on every one of them, and a new goal replaces the set again. Consumers: `ai/agents/frame.py` (two prompt lines), `ai/lead/edit_dispatch.py`, `ai/graph/state.py::record_questions`, `ai/graph/_lead_delta.py::_open_questions`. Red first with cases J and K.

**What you'd get.** `J`/`K new goal -> ['Plasmodium falciparum']`, `frame combination reqs -> []`, `organism hints -> ['Plasmodium falciparum']`.
