---
type: Backlog
---

# A key refused for its credit or its permissions is marked refused

`platform/key_refusals.py::classify_refusal` marks a researcher's key refused
only on the three bodies recorded with a made-up key
(`tests/fixtures/refusals/`): OpenAI 401 `invalid_api_key`, Anthropic 401
`authentication_error`, Google 400 `API_KEY_INVALID`. The providers' other
refusals of a valid key were not measured, because obtaining them needs an
account in that state: OpenAI 429 `insufficient_quota` and 403, Anthropic 400
on a low credit balance and 403 `permission_error`, Google 403
`PERMISSION_DENIED`.

Today such a key stays live: a turn on it fails with the provider's status
("the model provider answered 429"), and the next turn tries it again. The
check at entry (`probe_key`) already refuses to store it, by status. Record
each body with `python -m pathfinder.devtools.provider_refusals` against an
account in that state, add the recorder case, and classify it as `no_credit`
or `forbidden` (a new `KeyRefusal`, the row's CHECK and the settings sentence
move with it).
