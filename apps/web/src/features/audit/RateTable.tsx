"use client";

import type { AuditRunView } from "@pathfinder/shared/generated/types/AuditRunView";
import type { AuditWords } from "@pathfinder/shared/generated/types/AuditWords";
import type { GenomeRate } from "@pathfinder/shared/generated/types/GenomeRate";

import { gapText, rangeText, rateText, shareText, unresolvedText } from "./format";

const MEANINGS = [
  [
    "Rate",
    "The share of the checked candidates in the random sample whose gene model is wrong, with its 95% interval.",
  ],
  [
    "Range over every candidate",
    "The rate if every candidate that was not resolved were correct, up to the rate if every one were wrong.",
  ],
  [
    "Not judged",
    "Candidates the check could not judge, for example at an assembly gap. They are in neither count.",
  ],
  [
    "Not resolved",
    "Candidates the run did not check: outside the sample, not answered by the site, not read before the deadline, or not checkable.",
  ],
  [
    "BUSCO gap",
    "How many points of BUSCO completeness the genome's proteins lose against its DNA, as the site serves them.",
  ],
] as const;

function RateRow({
  rate,
  view,
  words,
}: {
  rate: GenomeRate;
  view: AuditRunView;
  words: AuditWords;
}) {
  const genome = view.genomes.find((row) => row.organism === rate.genome);
  return (
    <tr className="border-t border-border">
      <th scope="row" className="py-1 pr-4 font-normal">
        {rate.genome}
      </th>
      <td className="py-1 pr-4">{words.checks[rate.check]}</td>
      {rate.bounds === null ? (
        <td colSpan={3} className="py-1 pr-4">
          No judged finding
        </td>
      ) : (
        <>
          <td className="py-1 pr-4">{shareText(rate.bounds)}</td>
          <td className="py-1 pr-4">{rateText(rate.bounds)}</td>
          <td className="py-1 pr-4">{rangeText(rate.bounds)}</td>
        </>
      )}
      <td className="py-1 pr-4">{rate.unjudged}</td>
      <td className="py-1 pr-4">
        {unresolvedText(rate.unresolvedByStatus, words.unresolved)}
      </td>
      <td className="py-1">{genome === undefined ? "" : gapText(genome)}</td>
    </tr>
  );
}

export function RateTable({ view, words }: { view: AuditRunView; words: AuditWords }) {
  return (
    <div className="mt-3 text-sm">
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <caption className="text-left font-medium">
            Error rate in the random sample, by screened genome and check
          </caption>
          <thead>
            <tr>
              <th scope="col">Screened genome</th>
              <th scope="col">Check</th>
              <th scope="col">Errors of checked</th>
              <th scope="col">Rate (95% interval)</th>
              <th scope="col">Range over every candidate</th>
              <th scope="col">Not judged</th>
              <th scope="col">Not resolved</th>
              <th scope="col">BUSCO gap</th>
            </tr>
          </thead>
          <tbody>
            {view.rates.map((rate) => (
              <RateRow
                key={`${rate.genome} ${rate.check}`}
                rate={rate}
                view={view}
                words={words}
              />
            ))}
          </tbody>
        </table>
      </div>
      <h3 className="mt-3 font-medium">What the numbers mean</h3>
      <dl className="mt-1 text-xs">
        {MEANINGS.map(([term, meaning]) => (
          <div key={term} className="mt-1">
            <dt className="inline font-medium">{term}: </dt>
            <dd className="inline">{meaning}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-xs">
        An error the check traced to another genome&apos;s model counts as correct here,
        and the findings list it under that genome.
      </p>
    </div>
  );
}
