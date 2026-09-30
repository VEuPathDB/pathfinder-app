---
type: Backlog
---

# The Claude model is probed for images and documents

**Blocked on keys.** The deployment's OpenAI and Gemini keys answer the probe.
The Claude entry follows when the Anthropic account holds credit; nothing here
can be measured before that, and the user says when it is.

`platform/model_catalog.py` marks every OpenAI and Google model
`supports_images` and `supports_documents` from a live probe: one 1x1 PNG and
one one-page PDF sent on the deployment's key, both accepted with a 200 and the
PDF's word read back. The one Anthropic entry, `claude-haiku-4-5`, is marked
`False` because the probe could not measure it: every Anthropic call answered
400 with the provider's no-credit refusal, which measures the account, not the
model.

## What remains

- Add credit to the deployment's Anthropic account, or use a key that has it.
- Rerun the probe: `uv run python -m pathfinder.devtools.model_catalog probe
  anthropic:claude-haiku-4-5` prints the status of the image and the PDF and
  the two flags it measured.
- Set the two flags on the Claude entry from the measurement, with the probe
  table in `docs/knowledge/decisions/an-attachment-is-a-file-part-the-model-can-read.md`.

A model marked `False` refuses the attachment in the composer with the reason,
so the flags are safe while unmeasured; they are only conservative.
