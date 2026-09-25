---
type: Decision
title: An attachment is a file part the model can read
description: An image or a PDF the researcher attaches rides the message as an AI SDK v6 file part with a data URL, is stored in the event log with the message, and is refused by the composer and by the api when the model that reads the message does not read that kind or the message is over its caps. Which models read which kind is measured with one PNG and one PDF per catalog model. Uploading to PathFinder storage, converting images to text in the browser, and sending a file to a model that cannot read it were rejected.
tags: [decision, attachments, models, chat, security]
generated: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
status: stable
---

# What was decided

**A file rides the message.** The composer's `ChatAttachmentAdapter`
(`apps/web/src/features/conversation/runtime/chatAttachmentAdapter.ts`) turns
an image into an assistant-ui image part and a PDF into a file part, and
assistant-ui sends both as AI SDK v6 `file` UI parts: `type: "file"`,
`mediaType`, `filename`, and `url` as a `data:` URL. A gene-ID list (`.csv`,
`.tsv`, `.txt`) is still parsed in the browser and sent as text, because the
tools read the ids from the message text; the raw list file is not attached.

**The api keeps the file on the last message only.** `ChatRequestBody`
(`ai/conversation/request_body.py`) keeps the file parts of the message being
sent and drops those of every earlier message, because the worker reads
earlier turns from its checkpoint. The client drops them too
(`runtime/buildRequestBody.ts`), so a later turn does not upload the same bytes
again. The dispatcher writes the text and each file into the `user-message`
envelope of the event log, so a reload and a branch draw the thumbnail and the
file chip from the log (`content/parts/UserAttachments.tsx`).

**The caps are 10 MB per file, 20 MB per message and 6 files.** The event log
stores each file inside its row and the job payload carries the body, so a cap
bounds both. The composer refuses a file over a cap with a sentence and holds
Send while the message is over one; the api refuses the same message with a
problem detail before it is stored: 413 `ATTACHMENT_TOO_LARGE`, or 422
`ATTACHMENT_NOT_READABLE` for a kind no model reads here, a link instead of an
inline file, or a kind the reader does not read (`ai/conversation/attachments.py`,
`transport/http/routers/chat.py::refuse_unreadable_attachments`).

**The reader is the role that reads the message.** For PathFinder that is the
Lead; for site help it is its one agent (`assistants/registry.py::prompt_reader_model`,
`lib/models/attachments.ts::readerModel`). A pick for another role does not
decide what may be attached.

**Support is measured, not assumed.** `ModelEntry` carries `supports_images`
and `supports_documents`, `/api/v1/models` returns them, the model catalog
shows them, and the composer offers an image or a PDF only when the reader
reads it and names the models that do otherwise. The values come from sending
each cloud model one 1x1 PNG ("What colour is this image?") and one one-page
PDF that prints one word ("What single word is printed in this document?")
through pydantic-ai with the deployment's keys, on 2026-09-24:

| model | image (1x1 PNG) | PDF (one page) | PDF word read |
|---|---|---|---|
| `openai:gpt-5.6-sol` | accepted (200) | accepted (200) | yes |
| `openai:gpt-5.6-terra` | accepted (200) | accepted (200) | yes |
| `openai:gpt-5.6-luna` | accepted (200) | accepted (200) | yes |
| `anthropic:claude-opus-5` | refused (400) | refused (400) | no |
| `anthropic:claude-sonnet-5` | refused (400) | refused (400) | no |
| `anthropic:claude-haiku-4-5` | refused (400) | refused (400) | no |
| `google:gemini-3.1-pro-preview` | accepted (200) | accepted (200) | yes |
| `google:gemini-3.6-flash` | accepted (200) | accepted (200) | yes |
| `google:gemini-3.5-flash-lite` | accepted (200) | accepted (200) | yes |

Every Anthropic 400 carried the body "Your credit balance is too low to access
the Anthropic API", so the probe measured the account and not the model. The
Anthropic entries stay `false` until the same probe, run on an account with
credit, answers. The mock and every local model read no file.

# The model reads the file with the text

`build_turn_start` (`ai/conversation/_turn_helpers.py`) hands the message's
files to the runtime's `TurnStart.user_files`, and the runtime orders the
message as the files, then the text, in `TurnState.user_parts`. The Lead's run
starts from `TurnState.user_content` (`ai/graph/lead_node.py::_run_prompt`), so
its first request holds a `BinaryImage` or a `BinaryContent` beside the text,
and the checkpoint keeps them in the Lead's history for later turns. FRAME,
BUILD and VERIFY are handed the text alone, because they bind searches; the
title generator and the injection judge read the text alone too.

Measured through `pathfinder.devtools.chat --attach` on plasmodb with the
default Lead, `openai:gpt-5.6-luna`: a PNG of a three-row gene table answered
with the three ids and their products, and a one-page PDF of the same table
answered the same three ids.

# Input screening reads the text only

The injection judge reads the message text; an image or a PDF is not screened.
This is accepted for now: the file is the researcher's own upload into the
researcher's own thread, so an instruction hidden in it acts on the account of
the person who hid it.

# What was rejected

- **Uploading the file to PathFinder storage and sending a reference.** It adds
  a store, a retention policy and an access check for bytes that the provider
  needs inline anyway; the event log already carries the message it belongs to.
- **Converting an image to text in the browser (OCR) and sending the text.** It
  loses every table layout, figure and gel the researcher attached, and it puts
  a second reader in front of a model that reads the image itself.
- **Sending the file to a model that cannot read it and letting it fail.** The
  provider answers with a 400 after the message is stored and the turn opened,
  so the researcher learns late and the thread keeps a turn that did nothing.
