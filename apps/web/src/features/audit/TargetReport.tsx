"use client";

import { useId } from "react";
import type { AuditWords } from "@strategist/shared/generated/types/AuditWords";
import type { TargetReport as TargetReportView } from "@strategist/shared/generated/types/TargetReport";

import { plural, unresolvedText } from "./format";

export function TargetReport({
  report,
  words,
}: {
  report: TargetReportView;
  words: AuditWords;
}) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="mt-6 text-sm">
      <h2 id={headingId} className="text-base font-semibold">
        Your gene targets
      </h2>
      <p className="mt-1">
        These genes are in no rate: you chose them, so they are not a random sample.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-left">
          <caption className="sr-only">Gene targets by genome and check</caption>
          <thead>
            <tr>
              <th scope="col">Genome</th>
              <th scope="col">Check</th>
              <th scope="col">Checked</th>
              <th scope="col">Errors</th>
              <th scope="col">Not judged</th>
              <th scope="col">Not resolved</th>
            </tr>
          </thead>
          <tbody>
            {report.genomes.map((row) => (
              <tr key={`${row.genome} ${row.check}`} className="border-t border-border">
                <th scope="row" className="py-1 pr-4 font-normal">
                  {row.genome}
                </th>
                <td className="py-1 pr-4">{words.checks[row.check]}</td>
                <td className="py-1 pr-4">{row.checked}</td>
                <td className="py-1 pr-4">{row.errors}</td>
                <td className="py-1 pr-4">{row.unjudged}</td>
                <td className="py-1">
                  {unresolvedText(row.unresolvedByStatus, words.unresolved)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {report.unplaced > 0 ? (
        <p className="mt-2">
          {`${plural(report.unplaced, "target")} not placed in a genome: the run holds no genome for their genes.`}
        </p>
      ) : null}
    </section>
  );
}
