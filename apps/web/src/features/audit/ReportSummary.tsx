"use client";

import { useId } from "react";
import Link from "next/link";
import type { AuditRunView } from "@strategist/shared/generated/types/AuditRunView";
import type { ErrorTypeView } from "@strategist/shared/generated/types/ErrorTypeView";
import type { FindingLine } from "@strategist/shared/generated/types/FindingLine";

import { auditErrorTypeUrl, auditFindingUrl } from "@/lib/routes";

import { impactText, joinWords, plural } from "./format";
import { CERTAINTY_WORDS } from "./words";

const LINK = "text-primary underline-offset-2 hover:underline";

function ErrorTypeLine({ runId, type }: { runId: string; type: ErrorTypeView }) {
  const counted = `${plural(type.count, "finding")} in ${joinWords(type.genomes)}`;
  const certainty = CERTAINTY_WORDS[type.certainty].toLowerCase();
  return (
    <li className="mt-1">
      <Link href={auditErrorTypeUrl(runId, type.errorType)} className={LINK}>
        {type.title}
      </Link>
      {`: ${counted}, ${certainty}.`}
      {type.cause === null ? null : ` ${type.cause}`}
    </li>
  );
}

function lineText(line: FindingLine): string {
  const reviewed =
    line.reviewedImpact === null
      ? ""
      : `, reviewed impact ${String(line.reviewedImpact)}`;
  return `${line.genes.join(", ")} in ${line.genome}: impact ${impactText(line.impact)}${reviewed}`;
}

function FindingLink({
  runId,
  line,
  note,
}: {
  runId: string;
  line: FindingLine;
  note: string;
}) {
  return (
    <li className="mt-1">
      <Link href={auditFindingUrl(runId, line.id)} className={LINK}>
        {`${lineText(line)}${note}`}
      </Link>
    </li>
  );
}

function pendingText(view: AuditRunView): string {
  return view.reviewState === null
    ? "This run has not been reviewed."
    : `No summary yet: ${view.reviewState.text}`;
}

export function ReportSummary({ view }: { view: AuditRunView }) {
  const headingId = useId();
  const runId = view.run.id;
  const summarized = view.errorTypes.some((type) => type.cause !== null);
  const types = summarized
    ? view.errorTypes.filter((type) => type.cause !== null)
    : view.errorTypes;
  const reviewedLines = view.agreement !== null;
  return (
    <section aria-labelledby={headingId} className="mt-6 text-sm">
      <h2 id={headingId} className="text-base font-semibold">
        Headline findings
      </h2>
      {view.agreement === null ? null : <p className="mt-1">{view.agreement.text}</p>}
      {summarized ? null : <p className="mt-1">{pendingText(view)}</p>}
      {types.length === 0 ? null : (
        <ul className="mt-1">
          {types.map((type) => (
            <ErrorTypeLine key={type.errorType} runId={runId} type={type} />
          ))}
        </ul>
      )}
      {reviewedLines && view.headline.length > 0 ? (
        <ul className="mt-2">
          {view.headline.map((line) => (
            <FindingLink key={line.id} runId={runId} line={line} note="" />
          ))}
        </ul>
      ) : null}
      {reviewedLines && view.disputed.length > 0 ? (
        <>
          <h3 className="mt-3 font-medium">Findings the two reviews disagree on</h3>
          <ul className="mt-1">
            {view.disputed.map((line) => (
              <FindingLink
                key={line.id}
                runId={runId}
                line={line}
                note={
                  line.disagreementText === null ? "" : `. ${line.disagreementText}`
                }
              />
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
