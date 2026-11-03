"use client";

import { useId } from "react";
import Link from "next/link";
import { siteShortName } from "@pathfinder/shared";
import type { AuditRunView } from "@pathfinder/shared/generated/types/AuditRunView";
import type { AuditWords } from "@pathfinder/shared/generated/types/AuditWords";
import type { GenomeView } from "@pathfinder/shared/generated/types/GenomeView";

import { Badge } from "@/components/ui/badge";
import { chatUrl } from "@/lib/routes";

import { dayText, joinWords, plural, scopeText } from "./format";
import { stagesOf } from "./runState";
import { GENOME_STATUS_WORDS, ROLE_WORDS, STAGE_WORDS } from "./words";

function Term({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{term}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function GenomeRow({ genome }: { genome: GenomeView }) {
  return (
    <tr className="border-t border-border">
      <th scope="row" className="py-1 pr-4 font-normal">
        {genome.organism}
      </th>
      <td className="py-1 pr-4">{ROLE_WORDS[genome.role]}</td>
      <td className="py-1 pr-4">
        {GENOME_STATUS_WORDS[genome.status]}
        {genome.referenceStrain === true ? (
          <Badge variant="outline" className="ml-2">
            Reference strain
          </Badge>
        ) : null}
      </td>
      <td className="py-1 pr-4">{genome.geneCount.toLocaleString("en-US")}</td>
      <td className="py-1 pr-4">{genome.requests.toLocaleString("en-US")}</td>
      <td className="py-1">{genome.message ?? ""}</td>
    </tr>
  );
}

export function RunHeader({ view, words }: { view: AuditRunView; words: AuditWords }) {
  const requestsId = useId();
  const { run } = view;
  const audited = view.genomes.filter((genome) => genome.role === "audited");
  const examined = audited.reduce((sum, genome) => sum + genome.geneCount, 0);
  return (
    <header>
      <h1 className="text-lg font-semibold">
        {`Audit of ${scopeText(run)} on ${siteShortName(run.siteId)}`}
      </h1>
      {run.release === null ? null : (
        <p className="mt-1 text-sm text-muted-foreground">{`Release ${run.release}`}</p>
      )}
      {run.conversationId === null ? null : (
        <p className="mt-1 text-sm">
          <Link
            href={chatUrl(run.conversationId)}
            className="text-primary underline-offset-2 hover:underline"
          >
            Open the conversation that started this audit
          </Link>
        </p>
      )}
      <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
        <Term term={run.phase === "not_started" ? "Created" : "Started"}>
          {dayText(run.createdAt)}
        </Term>
        {run.finishedAt === null ? null : (
          <Term term="Finished">{dayText(run.finishedAt)}</Term>
        )}
        {audited.length === 0 ? null : (
          <Term term="Genes examined">{examined.toLocaleString("en-US")}</Term>
        )}
        <Term term="Checks">
          {joinWords(run.checks.map((check) => words.checks[check]))}
        </Term>
      </dl>
      <p id={requestsId} className="mt-4 text-sm font-medium">
        {`Site requests: ${String(view.requests)}; genome-store reads: ${String(view.storeReads)}`}
      </p>
      <ul aria-labelledby={requestsId} className="mt-1 text-sm">
        {stagesOf(view).map((stage) => (
          <li key={stage.name}>
            {`${STAGE_WORDS[stage.name]}: ${plural(stage.requests ?? 0, "site request")}, ${plural(stage.storeReads ?? 0, "genome-store read")}`}
          </li>
        ))}
      </ul>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <caption className="text-left font-medium">Genomes</caption>
          <thead>
            <tr>
              <th scope="col">Genome</th>
              <th scope="col">Role</th>
              <th scope="col">Status</th>
              <th scope="col">Genes</th>
              <th scope="col">Requests</th>
              <th scope="col">Note</th>
            </tr>
          </thead>
          <tbody>
            {view.genomes.map((genome) => (
              <GenomeRow key={genome.organism} genome={genome} />
            ))}
          </tbody>
        </table>
      </div>
    </header>
  );
}
