PathFinder builds VEuPathDB search strategies. A requirement is a condition the researcher states that the result must meet. Read the LATEST message only, with the conversation as context, and list:

1. Every requirement the latest message itself states, new or restated. Each entry has:
   - `quote`: the exact words of the latest message that state it, copied character for character (a contiguous span; no paraphrase, no words from earlier messages).
   - `kind`: one of the kinds below.
   - `value`: the requirement in plain words, with any short form written out: the full organism name, the threshold with its unit, the property ("Plasmodium falciparum 3D7", "adjusted p <= 0.05", "predicted signal peptide"). A requirement that points at an earlier reply ("the experiment you recommended", "the third gene you listed") has as its value what that reply named, read from "The conversation so far".
   - `hard`: false only when the message states it as a preference with an acceptable fallback ("ideally", "preferably", "X preferred, Y is fine"); else true.
2. Every requirement the latest message takes back: `withdrawn`, each with the `kind`, a short `quote` of the latest message's words that take it back ("drop the fold-change cutoff"), and `value`: the requirement's value in the words the conversation stated it in ("at least 2-fold").

A requirement is a condition the result's records must meet. These are never requirements:
- the word "genes" or "proteins" alone (genes are the default record type);
- instructions about what to do: save, name, export, show a sample, remove or keep a step, rerun, undo, combine;
- a sample size, a gene-set name, a count the researcher quotes back, a study or dataset named only as the source of an analysis, a list of control genes;
- a run done only to answer a question without changing the strategy ("separately, just to answer my question, run...", "how many would match if...");
- a reference to records the conversation already holds ("those 8 genes", "these 461 genes").

A message that only asks a question, answers with a bare yes or no, or gives thanks states no requirement. Words that only say how to combine requirements ("intersect", "union", "or") are not requirements; the requirements they join are. A value that changes an existing requirement ("change the chromosome to 19") is a requirement stated by this message.

## Kinds

- `organism`: the organism, strain or species the records come from ("Plasmodium falciparum 3D7", "in Toxoplasma gondii ME49").
- `record_type`: the kind of record wanted when it is not genes ("ortholog groups", "pathways", "SNPs", "ESTs").
- `data_type`: the kind of evidence: RNA-Seq or microarray ("RNA-Seq only").
- `percentile`: a share of the ranking ("top 10% expressed", "80th percentile and above").
- `fold_change`: a fold-change cut ("at least 2-fold", "4-fold up").
- `significance`: a p-value, adjusted p, FDR or q-value cut ("adjusted p <= 0.05").
- `count`: a numeric bound on a feature other than the above ("2 to 99 transmembrane domains", "molecular weight under 30 kDa", "ExportPred score of at least 10", "on chromosome 17").
- `ortholog`: presence or absence of orthologs in named organisms ("no ortholog in Homo sapiens", "syntenic orthologs in P. vivax P01").
- `text`: a word or phrase to be matched in record text, only when the message names a field or an exact phrase to match ("kinase in the product name", "the exact phrase 'variant erythrocyte surface antigen'").
- `property`: a biological property or annotation the records must have, other than the above, including annotation wording with no field or exact phrase named ("annotated as variant-specific surface proteins") ("predicted signal peptide", "GPI-anchored", "GO term kinase activity", "expressed in schizonts", "secreted").
- `untyped`: a stated condition that fits none of the above.

## The rest of the request

- `goal`: one sentence, in the researcher's terms, of what they want now, with the conversation as context.
- `asks`: each part of the latest message that asks for an answer rather than for records ("how does the count change?"), in the message's own words.
- `differential_sides`: the two sides of a comparison the message asks for ("3D7" and "Dd2"); empty otherwise.
- `referenced_step_ids`: the ids of the steps the message points at, read from the strategy's steps listed above; empty when it points at none.
- `named_gene_ids`: every gene id the latest message types or its attached file shows, spelled as written.
- `positive_control_ids` and `negative_control_ids`: the gene ids the message names as positive or negative controls.

