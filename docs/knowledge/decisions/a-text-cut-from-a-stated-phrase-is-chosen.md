---
type: Decision
title: A text cut from a stated phrase is chosen
description: Who set a free-text value is decided against the requirement phrases. A text that leaves out the words a requirement writes before it is chosen; the phrase it was cut from is never counted as a reading.
tags: [parameters, provenance, correctness]
generated: { by: claude-code/opus-5.5, at: 2026-09-30T00:00:00Z }
status: stable
---

# A text cut from a stated phrase is chosen

## Rule

- `value_source.cut_from` reads the thread's requirement phrases. A string value
  is cut when a phrase holds its words whole after a word that is not filler.
  Such a value is `chosen`, never `stated`. Its readings are derived from the
  bound text alone ([an assumed value is recorded](an-assumed-value-is-recorded-not-narrated.md)):
  the phrase reading of an unquoted text, the words reading of a quoted one.
- Only the words before the value count. Words before a noun phrase modify it;
  a word after it ("annotation", "domain", "genes") names what kind of evidence
  the phrase asks for.
- A number is never cut: it states a quantity, and "chromosome 1 positions 1000
  to 5000" narrows no start of 1000. A text a request message writes between
  quotes, compared with the quotes stripped and the case folded, is the
  researcher's whole term and is never cut, so `"GPI anchored"` stays stated
  beside the requirement "exact quoted phrase GPI anchored".
- Whether the value is unset is read when it binds, on the published sheet
  ([an assumed value is recorded](an-assumed-value-is-recorded-not-narrated.md)).

## Rejected

- **Any content word of the requirement phrase makes the value a cut.** The
  requirement "cysteine-rich protein annotation" would mark the text
  "cysteine-rich protein" chosen, although the researcher wrote those words.
- **The researcher's message in place of the requirement phrases.** An
  organism written before the text ("Plasmodium falciparum 3D7 kinase genes")
  would mark every text after it chosen; the requirements hold the organism apart.
- **The phrase the text was cut from counted as a reading.** A requirement
  phrase is a sentence, not a search term: the cut of "whose product is variant
  surface glycoprotein" was sent as a text and counted 987 genes beside the
  bound phrase's 768, and the cut "phrase GPI anchored" was shown as the phrase
  reading of `"GPI anchored"` at the words count. No search runs either text.

## Anchors

- giardiadb GenesByText in G. muris: the context read answers `text_expression`
  with the bound text as its initial value (published: `*reductase`). The
  unquoted text counts 4,497 genes, the quoted phrase 0.
- piroplasmadb GenesByText in B. bovis T2Bo: "erythrocyte surface antigen" and
  "variant erythrocyte surface antigen" each count 153 genes unquoted; the
  quoted phrase counts 1.
- tritrypdb GenesByText: the quoted `"GPI anchored"` counts 1 gene and the
  unquoted `GPI anchored` 12.
