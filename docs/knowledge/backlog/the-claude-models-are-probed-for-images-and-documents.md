---
type: Backlog
---

# The Claude models are probed for images and documents

**Blocked on keys.** The deployment runs the OpenAI models for now. Gemini and
Claude follow when their accounts hold credit; nothing here can be measured
before that, and the user says when it is.

`ai/models/catalog.py` marks every OpenAI and Google model `supports_images`
and `supports_documents` from a live probe: one 1x1 PNG and one one-page PDF
sent through pydantic-ai on the deployment's key, both accepted with a 200 and
the PDF's word read back. The three Anthropic entries are marked `False`
because the probe could not measure them: all six Anthropic calls answered
400 "Your credit balance is too low", which measures the account, not the
model.

## What remains

- Add credit to the deployment's Anthropic account, or use a key that has it.
- Rerun the probe (the script is kept in the session mirror as
  `a16/probe-modalities.py`; it prints one row per catalog model with the
  provider's status for the image and the PDF).
- Set the two flags on the three Claude entries from the measurement, with the
  probe table in `docs/knowledge/decisions/an-attachment-is-a-file-part-the-model-can-read.md`.

A model marked `False` refuses the attachment in the composer with the reason,
so the flags are safe while unmeasured; they are only conservative.
