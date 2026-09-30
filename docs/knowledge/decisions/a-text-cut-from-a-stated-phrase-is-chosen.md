---
type: Decision
title: A text cut from a stated phrase is chosen, and its unset test reads the published sheet
description: Who set a free-text value is decided against the requirement phrases and the value the site publishes. A text that leaves out the words a requirement writes before it is chosen; a value is unset only at the published initial value, never at a sheet read under the bound values.
tags: [parameters, provenance, correctness]
generated: { by: claude-code/opus-5.5, at: 2026-09-30T00:00:00Z }
status: stable
---

# A text cut from a stated phrase is chosen

## Rule

- `value_source.cut_from` reads the thread's requirement phrases. A string value
  is cut when a phrase holds its words whole after a word that is not filler.
  Such a value is `chosen`, never `stated`, and `BoundValue.stated_as` holds the
  longer phrase. `measure_binding` counts that phrase as a `wildcard_phrase`
  reading, so the clause and the assumed-value caveat show its count.
- Only the words before the value count. Words before a noun phrase modify it;
  a word after it ("annotation", "domain", "genes") names what kind of evidence
  the phrase asks for.
- A value is unset only at the initial value the published sheet holds.
  `_frame_measure.infos_under` reads vocabularies under the bound values and
  keeps each parameter's published initial value, because WDK answers every
  sent value as that parameter's `initialDisplayValue`.

## Rejected

- **Any content word of the requirement phrase makes the value a cut.** The
  requirement "cysteine-rich protein annotation" would mark the text
  "cysteine-rich protein" chosen, although the researcher wrote those words.
- **The researcher's message in place of the requirement phrases.** An
  organism written before the text ("Plasmodium falciparum 3D7 kinase genes")
  would mark every text after it chosen; the requirements hold the organism apart.
- **Pass the published sheet to `measure_binding` beside the context sheet.**
  Every caller of the context read then owns the choice again. `infos_under` is
  the one function every context read goes through, so the published initial
  value is set once there, and `pick_readings._site_default` reads it too.

## Anchors

- giardiadb GenesByText in G. muris: the context read answers `text_expression`
  with the bound text as its initial value (published: `*reductase`). The
  unquoted text counts 4,497 genes, the quoted phrase 0.
- piroplasmadb GenesByText in B. bovis T2Bo: "erythrocyte surface antigen" and
  "variant erythrocyte surface antigen" each count 153 genes unquoted; the
  quoted phrase counts 1.
