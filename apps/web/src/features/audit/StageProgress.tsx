"use client";

import { useId } from "react";
import type { AuditRunView } from "@strategist/shared/generated/types/AuditRunView";
import type { AuditWords } from "@strategist/shared/generated/types/AuditWords";
import type { ReviewState } from "@strategist/shared/generated/types/ReviewState";
import type { StageRecord } from "@strategist/shared/generated/types/StageRecord";

import { plural } from "./format";
import { currentStage, leftLines, leftLineText, stagesOf } from "./runState";
import { PHASE_WORDS, STAGE_WORDS } from "./words";

function phaseText(view: AuditRunView): string {
  const phase = view.run.phase;
  const message = currentStage(view)?.message ?? "";
  const live = phase === "running" || phase === "queued";
  return live && message !== ""
    ? `${PHASE_WORDS[phase]}: ${message}`
    : PHASE_WORDS[phase];
}

function reviewLine(state: ReviewState): string {
  const line = `${state.text}: ${String(state.done)} of ${plural(state.total, "finding")}`;
  return state.message === "" ? line : `${line}: ${state.message}`;
}

function StageRow({ stage }: { stage: StageRecord }) {
  const id = useId();
  const finished = stage.finished === true;
  const done = stage.done ?? 0;
  const total = stage.total ?? 0;
  const empty = finished && total === 0;
  return (
    <li className="mt-2">
      <label htmlFor={id} className="block">
        {STAGE_WORDS[stage.name]}
      </label>
      <progress
        id={id}
        className="w-full"
        value={empty ? 1 : done}
        max={Math.max(total, 1)}
      />
      <span className="mr-3 text-xs">
        {finished ? "Done" : `${String(done)} of ${String(total)}`}
      </span>
      <span className="text-xs text-muted-foreground">
        {`${plural(stage.requests ?? 0, "site request")}, ${plural(stage.storeReads ?? 0, "genome-store read")}`}
      </span>
    </li>
  );
}

export function StageProgress({
  view,
  words,
}: {
  view: AuditRunView;
  words: AuditWords;
}) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="mt-6 text-sm">
      <h2 id={headingId} className="text-base font-semibold">
        Progress
      </h2>
      <p role="status" className="mt-1">
        {phaseText(view)}
      </p>
      {view.halt === null ? null : (
        <div className="mt-2 rounded border border-border p-3">
          <p>{words.halts[view.halt.kind]}</p>
          {view.halt.kind === "task_failed" ? (
            <details className="mt-1 text-xs">
              <summary>Technical detail</summary>
              <code>{view.halt.detail}</code>
            </details>
          ) : null}
        </div>
      )}
      <ol>
        {stagesOf(view).map((stage) => (
          <StageRow key={stage.name} stage={stage} />
        ))}
      </ol>
      {view.reviewState === null ? null : (
        <p className="mt-2">{reviewLine(view.reviewState)}</p>
      )}
      {(view.left.refused ?? 0) > 0 ? (
        <p className="mt-2">
          {`Refused for your sign-in, and read again on a retry: ${plural(view.left.refused ?? 0, "unit")}`}
        </p>
      ) : null}
      {leftLines(view).map((line) => (
        <p key={line.status} className="mt-2">
          {leftLineText(line, words)}
        </p>
      ))}
    </section>
  );
}
