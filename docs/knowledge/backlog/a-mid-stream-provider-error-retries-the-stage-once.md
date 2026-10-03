---
type: Backlog
title: A mid-stream provider error retries the stage once
description: A provider error raised inside a model's stream ends the whole turn with a stop reply, although the same request sent again usually completes; the stage's model request is retried once before the turn stops.
tags: [lead, providers, resilience]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# A mid-stream provider error retries the stage once

**What I did.** Built on the portal "Genes across Cryptosporidium with the GO term 'protein glycosylation'"; FRAME bound seven current terms (426 genes) and VERIFY started on `gpt-6-luna`.

**What I got.** The provider raised `openai.APIError` inside the verification stream (status None, no refusal classification), the guard rebuilt it as `ModelAPIError("The provider did not complete the request to gpt-6-luna.")`, and the turn ended with "I stopped this turn on an error I could not recover from ... The Checking stage of this turn runs GPT-6 Luna, and it did not answer. Choose a different model for that stage in Settings, or send the message again". A one-token request on the same key completed a minute later.

**Why that's wrong.** A transient failure of one model call costs the researcher the whole turn and the built strategy's check, and the reply suggests a model change for a fault that is not the model's.

**Why it happens.** pydantic-ai does not wrap or retry an error the provider SDK raises after the stream opened, and `GuardedModel` (`platform/model_keys.py`) only classifies and strips it. Nothing re-sends the stage's request.

**Fix.** `GuardedModel` (or a pydantic-ai `FallbackModel` over the same model) re-sends the request once when a provider error is neither a refusal nor a 4xx, before the turn's own stream sees it; if the retry fails too, the stop reply says the provider did not complete the request twice and offers a resend, never a model change. Verify against the installed pydantic-ai how `FallbackModel.request_stream` treats an error raised during iteration, since the retry has to happen before any event reached the consumer.

**What you'd get.** The check completes on the second request; when both fail, "the provider did not complete the Checking stage twice; send the message again" and no advice to switch models.
