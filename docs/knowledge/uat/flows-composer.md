---
type: TestPlan
title: UAT flows - composer
description: Every slash command, and attachments - a gene-id list, an image, a PDF, a kind PathFinder refuses, and the size and count caps - with the exact sentences of each refusal.
tags: [uat, flows, composer, slash-commands, attachments]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: draft
---

# Composer (C)

On plasmodb. The input's placeholder is `Ask about strategies, genes, or data... (try /help)`. The slash menu opens when the input starts with `/` and holds no space; ArrowUp and ArrowDown move, Enter or Tab picks, Escape clears.

## Test files

| File | Content | Used by |
|---|---|---|
| `controls.csv` | three lines: `geneId,product`, `PF3D7_0709000,CRT`, `PF3D7_1133400,AMA1` | C12 |
| `table.png` | a PNG, white opaque background, of the table `Gene ID / Product`: `PF3D7_0709000 chloroquine resistance transporter`, `PF3D7_1133400 apical membrane antigen 1`, `PF3D7_0102600 unspecified product` | C13 |
| `table-transparent.png` | the same table with a transparent background | C13 step 3 |
| `table.pdf` | the same table as a one-page PDF | C14 |
| `table.zip` | any zip file | C15 |
| `big.png` | any PNG over 10 MB (the measurement padded `table.png` to 11.0 MB) | C16 |
| seven small PNGs | any | C16 |

## C1 - `/help` and the menu - core

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation, composer | Type `/` | Menu `Slash commands` with, in this order: `/new`, `/rename`, `/export` (aliases `/save /download`), `/import`, `/help` (alias `/?`), `/clear`, `/analyze`, `/summarize`, `/diagnose`, `/explain` |
| 2 | Menu | Hover `/clear` | Greyed; tooltip `This conversation has no strategy yet.` (so are `/analyze`, `/diagnose`, `/explain`) |
| 3 | Composer | Type `/hel`, Enter | The input reads `/` again; nothing is sent |

## C2 to C11 - One flow per command

| Id | Command | Do | Expect |
|---|---|---|---|
| C2 | `/new` | Pick it | A new draft conversation, default assistant |
| C3 | `/rename` | Pick it, type `UAT rename C3`, `Next` | Toast `Renamed to "UAT rename C3".`; empty name: `Name cannot be empty.` |
| C4 | `/export` | Pick it on a conversation with no strategy, choose `Current strategy (JSON)` | Toast `This conversation has no strategy yet.`; nothing downloads |
| C5 | `/export` | On the S2 conversation: `This conversation (Markdown)`, then `This conversation (JSON)`, then `Current strategy (JSON)` | Downloads `chat-<conversation id>.md` (starts `# PathFinder conversation export`, one `## user` / `## assistant` per message), `chat-<id>.json`, `strategy-<id>.json`; toasts `Conversation exported.`, `Strategy downloaded.` |
| C6 | `/export` | `Latest gene set on this site (CSV)`, then `(TXT)`, after G1 | Toast `Downloading <file name>`; the CSV holds the gene set's 116 ids. With no gene set: `No gene sets to export.` |
| C7 | `/import` | Name `UAT import C7`, ids `PF3D7_0102600` newline `PF3D7_0709000, PF3D7_1133400`, `Continue` | Toast `Imported "UAT import C7" with 3 gene IDs.`; empty name `Name required.`; no ids `Paste at least one gene ID.` |
| C8 | `/clear` | On the S2 conversation | Sends `Clear the current strategy by calling clear_strategy with confirm=true.`; the approval card of S13 |
| C9 | `/analyze` | On the S2 conversation | Fills the input (does not send) with `Analyze my current strategy. Summarize topology and step flow, any weak spots or redundant steps, concrete improvement suggestions, and what I should try next.`; `Send` gives an analysis of the 3-step INTERSECT and no change to the strategy. Measured: no analysis text at all, only a proposal card with three changes (FND-14, major); 36 s, $0.016 |
| C10 | `/summarize` | Any conversation | Fills `Summarize this conversation so far: the research question, the strategy I've built, key decisions made, and anything still open.`; the reply summarizes; nothing is built |
| C11 | `/diagnose`, `/explain` | On the N4 conversation (0 genes), `/diagnose`; then `/explain`, hint `the transmembrane step` | `/diagnose` fills `Diagnose my current strategy. Call get_live_strategy_state, walk through each step's count, and identify where results collapse. Suggest the likely cause and concrete fixes.`; the reply names the step that returns 0. `/explain` fills `Explain what the transmembrane step does and why it matters biologically.` |

Two prefills put code names in front of the researcher (`clear_strategy`, `get_live_strategy_state`); record them as a minor if they still show.

## C12 - A gene-id list - core

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Composer | `Attach`, pick `controls.csv` | A chip `controls.csv` |
| 2 | Composer | Type `Use these genes as my positive controls.`, Send | The sent message holds the text and `Attached gene-ID list from controls.csv: PF3D7_0709000, PF3D7_1133400`; the reply takes both as positive controls and either saves a control set (trace row `Build control set`) or asks for negative controls. Measured: it asked for negatives ("I also need at least one negative-control gene"), 8 s of model time, $0.008 |

## C13 - An image - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Settings, `Model` | Keep the default model (`GPT-5.6 Luna`) | `Attach` reads `Attach a gene-ID list, an image or a PDF` |
| 2 | New conversation | Attach `table.png`, send `Which genes are in this image?` | A thumbnail in the user message; the reply lists PF3D7_0709000, PF3D7_1133400, PF3D7_0102600; after a reload the thumbnail is still there |
| 3 | New conversation | The same with `table-transparent.png` | The same three genes |

Measured: step 2 listed the three genes in 2 of 2 runs (about 18 s, $0.009). Step 3 failed 3 of 3: twice classified off-topic, once "it appears completely black" (FND-13, minor).

## C14 - A PDF - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Attach `table.pdf`, send `Which genes are in this document?` | A file chip `table.pdf` in the user message; the reply lists the three genes. Measured: 26 s, $0.011 |

## C15 - A kind PathFinder refuses

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Composer | `Attach`, pick `table.zip` | The chooser does not offer it; when forced, toast `PathFinder reads gene-ID lists (.csv, .tsv, .txt), images (PNG, JPEG, WebP, GIF) and PDFs.` |
| 2 | The chat api (from a script, when the composer cannot send it) | Send it anyway | 422 `ATTACHMENT_NOT_READABLE`, detail `table.zip is application/zip; PathFinder reads PNG, JPEG, WebP and GIF images and PDF documents.` (measured) |

## C16 - The size and count caps

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Composer | Attach `big.png` (11.0 MB) | Toast `big.png is 11.0 MB; one attachment can be at most 10 MB.`; no chip. The api refuses the same with 413 `ATTACHMENT_TOO_LARGE` and the same sentence (measured) |
| 2 | Composer | Attach seven small PNGs | Alert `One message can carry at most 6 attachments; this one has 7.`; `Send` disabled; Enter does nothing |
| 3 | Composer | Attach PNGs totalling over 20 MB | Alert `These attachments come to <n> MB; one message can carry at most 20 MB.`; `Send` disabled |
