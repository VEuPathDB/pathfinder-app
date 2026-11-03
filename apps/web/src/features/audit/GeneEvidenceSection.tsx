import { useId } from "react";
import type { GeneEvidence } from "@pathfinder/shared/generated/types/GeneEvidence";
import type { GeneEvidencePayload } from "@pathfinder/shared/generated/types/GeneEvidencePayload";
import type { GeneTranscript } from "@pathfinder/shared/generated/types/GeneTranscript";
import type { PhenotypeScreen } from "@pathfinder/shared/generated/types/PhenotypeScreen";
import type { SeqEdit } from "@pathfinder/shared/generated/types/SeqEdit";

import { joinWords, plural } from "./format";
import { EVIDENCE_KIND_WORDS } from "./words";

const SMALL_EVALUE = 0.001;

function servedName(name: string): string {
  return name.replace(/<[^>]*>/g, "").replaceAll("_", " ");
}

function evalueText(evalue: number): string {
  return evalue > 0 && evalue < SMALL_EVALUE ? evalue.toExponential(2) : String(evalue);
}

function transcriptText(transcript: GeneTranscript): string {
  const protein =
    transcript.proteinLength === null
      ? "no protein length served"
      : plural(transcript.proteinLength, "residue");
  return `${transcript.transcriptId}: ${protein}, ${plural(transcript.exonCount, "exon")}`;
}

function seqEditText(edit: SeqEdit): string {
  const fields: [string, string | null][] = [
    ["kind", edit.kind],
    ["length change", edit.lengthDiff],
    ["location", edit.location],
    ["change", edit.diff],
  ];
  return fields
    .flatMap(([label, value]) => (value === null ? [] : [`${label}: ${value}`]))
    .join(", ");
}

function screenRowText(row: PhenotypeScreen["rows"][number]): string {
  return Object.entries(row)
    .flatMap(([key, value]) =>
      value === null ? [] : [`${key.replaceAll("_", " ")}: ${value}`],
    )
    .join(", ");
}

function screenText(screen: PhenotypeScreen): string {
  return `${servedName(screen.table)}: ${screen.rows.map(screenRowText).join("; ")}`;
}

function peptidesText(record: GeneEvidence): string {
  if (record.peptides.length === 0) return "No mass-spec peptide served";
  const spectra = record.peptides.reduce(
    (total, peptide) => total + peptide.spectra,
    0,
  );
  return `${plural(record.peptides.length, "mass-spec peptide")}, ${plural(spectra, "spectrum", "spectra")}`;
}

function TextList({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="space-y-0.5">
      {items.map((item, index) => (
        <li key={`${String(index)}-${item}`}>{item}</li>
      ))}
    </ul>
  );
}

function PdbTable({ record }: { record: GeneEvidence }) {
  if (record.pdbHits.length === 0) return <p>No PDB similarity served</p>;
  return (
    <table className="w-full text-left">
      <caption className="text-left font-medium">
        {`PDB similarities of ${record.gene}: ${String(record.pdbHits.length)}`}
      </caption>
      <thead className="text-muted-foreground">
        <tr>
          <th scope="col">PDB id</th>
          <th scope="col">Title</th>
          <th scope="col">Taxon</th>
          <th scope="col">Identity</th>
          <th scope="col">Protein covered</th>
          <th scope="col">E-value</th>
        </tr>
      </thead>
      <tbody>
        {record.pdbHits.map((hit) => (
          <tr key={`${hit.transcript}-${hit.pdbId}`} className="border-t border-border">
            <td>{hit.pdbId}</td>
            <td>{hit.title}</td>
            <td>{hit.taxon}</td>
            <td>{`${String(hit.identity)}%`}</td>
            <td>{`${String(hit.proteinCoveredPercent)}%`}</td>
            <td>{evalueText(hit.evalue)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function GeneRecord({ record }: { record: GeneEvidence }) {
  const screens = [...record.phenotypes, ...record.unprefixedTables].filter(
    (screen) => screen.rows.length > 0,
  );
  return (
    <div className="mt-3 space-y-2 text-xs">
      <h4 className="font-medium">
        {`${record.gene}: ${plural(record.pubmed, "PubMed article")}, ${plural(record.comments, "comment")}, ${plural(record.notes, "note")}`}
      </h4>
      <TextList items={record.transcripts.map(transcriptText)} />
      <TextList
        items={record.alphafold.map(
          (model) =>
            `AlphaFold ${model.uniprotId} (${model.source}): residues ${String(model.first)} to ${String(model.last)} of ${String(model.length)}`,
        )}
      />
      <PdbTable record={record} />
      <p>{peptidesText(record)}</p>
      <TextList
        items={record.linkouts.map(
          (link) => `${servedName(link.database)}: ${link.externalId}`,
        )}
      />
      {record.seqedits.length === 0 ? (
        <p>No sequence edit served</p>
      ) : (
        <TextList items={record.seqedits.map(seqEditText)} />
      )}
      {screens.length === 0 ? (
        <p>No phenotype screen holds a row for this gene</p>
      ) : (
        <TextList items={screens.map(screenText)} />
      )}
      {record.unserved.length === 0 ? null : (
        <p>{`Tables the site does not serve: ${joinWords(record.unserved)}`}</p>
      )}
    </div>
  );
}

export function GeneEvidenceSection({ evidence }: { evidence: GeneEvidencePayload }) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="mt-4">
      <h3 id={headingId} className="text-sm font-semibold">
        {EVIDENCE_KIND_WORDS.gene_evidence}
      </h3>
      {evidence.evidence.map((record) => (
        <GeneRecord key={record.gene} record={record} />
      ))}
    </section>
  );
}
