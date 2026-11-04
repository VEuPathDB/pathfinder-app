import type { AuditWords } from "@pathfinder/shared/generated/types/AuditWords";
import type { EvidenceView } from "@pathfinder/shared/generated/types/EvidenceView";
import type { Fact } from "@pathfinder/shared/generated/types/Fact";
import type { GeneEvidence } from "@pathfinder/shared/generated/types/GeneEvidence";
import type { GeneTranscript } from "@pathfinder/shared/generated/types/GeneTranscript";
import type { PhenotypeScreen } from "@pathfinder/shared/generated/types/PhenotypeScreen";
import type { SeqEdit } from "@pathfinder/shared/generated/types/SeqEdit";

import { joinWords, plural } from "./format";
import { ProteinFigure } from "./ProteinFigure";
import { evidenceTracks } from "./proteinTracks";
import { EvidenceRegion } from "./RelativesSection";

const SMALL_EVALUE = 0.001;
const PDB_TABLE = "PdbSimilarities";
const PEPTIDE_TABLE = "MassSpecDownload";
const SEQEDIT_TABLE = "Seqedits";
const COMMENT_TABLE = "UserComments";
const PUBMED_TABLE = "PubMed";
const NOTE_TABLE = "Notes";

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

function countText(
  record: GeneEvidence,
  table: string,
  count: number,
  word: string,
): string {
  return record.unserved.includes(table) ? `${word}s not served` : plural(count, word);
}

function headingText(record: GeneEvidence): string {
  const counts = [
    countText(record, PUBMED_TABLE, record.pubmed, "PubMed article"),
    countText(record, COMMENT_TABLE, record.comments, "comment"),
    countText(record, NOTE_TABLE, record.notes, "note"),
  ];
  return `${record.gene}: ${counts.join(", ")}`;
}

function noScreenText(record: GeneEvidence, evidenceTables: string[]): string {
  return record.unserved.some((table) => !evidenceTables.includes(table))
    ? "No screen the site served holds a row for this gene, and not every screen was served"
    : "No phenotype screen holds a row for this gene";
}

function peptidesText(record: GeneEvidence): string {
  if (record.unserved.includes(PEPTIDE_TABLE)) return "Mass-spec peptides not served";
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
  if (record.unserved.includes(PDB_TABLE)) return <p>PDB similarities not served</p>;
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

function GeneRecord({
  record,
  evidenceTables,
}: {
  record: GeneEvidence;
  evidenceTables: string[];
}) {
  const screens = [...record.phenotypes, ...record.unprefixedTables].filter(
    (screen) => screen.rows.length > 0,
  );
  return (
    <div className="mt-3 space-y-2 text-xs">
      <h4 className="font-medium">{headingText(record)}</h4>
      <TextList items={record.transcripts.map(transcriptText)} />
      <ProteinFigure
        title={`Protein lengths of the transcripts of ${record.gene}`}
        tracks={evidenceTracks(record)}
      />
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
      {record.unserved.includes(SEQEDIT_TABLE) ? (
        <p>Sequence edits not served</p>
      ) : record.seqedits.length === 0 ? (
        <p>No sequence edit served</p>
      ) : (
        <TextList items={record.seqedits.map(seqEditText)} />
      )}
      {screens.length === 0 ? (
        <p>{noScreenText(record, evidenceTables)}</p>
      ) : (
        <TextList items={screens.map(screenText)} />
      )}
      {record.unserved.length === 0 ? null : (
        <p>{`Tables the site does not serve: ${joinWords(record.unserved)}`}</p>
      )}
    </div>
  );
}

export function GeneEvidenceSection({
  evidence,
  facts,
  words,
}: {
  evidence: EvidenceView;
  facts: readonly Fact[];
  words: AuditWords;
}) {
  const { payload } = evidence;
  return (
    <EvidenceRegion
      evidence={evidence}
      facts={facts}
      words={words}
      figures={
        payload?.kind === "gene_evidence"
          ? payload.evidence.map((record) => (
              <GeneRecord
                key={record.gene}
                record={record}
                evidenceTables={words.evidenceTables}
              />
            ))
          : null
      }
    />
  );
}
