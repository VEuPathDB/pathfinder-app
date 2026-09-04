"use client";

import type { Criterion } from "@pathfinder/shared/generated/types/Criterion";
import type { InvestigationLedger } from "@pathfinder/shared/generated/types/InvestigationLedger";
import type { NodeResult } from "@pathfinder/shared/generated/types/NodeResult";

import { MessageResponse } from "@/components/ai-elements/message";
import { formatParamValue } from "@/lib/parameters/paramValue";
import { type Tone } from "@/features/conversation/rail/statusTone";

import { StatusPill } from "./LedgerPanelPrimitives";

function Markdown({ children }: { children: string }) {
  return (
    <div className="min-w-0 break-words text-[11px] leading-relaxed [&_a]:break-all [&_code]:whitespace-pre-wrap [&_code]:break-all [&_pre]:overflow-x-auto">
      <MessageResponse>{children}</MessageResponse>
    </div>
  );
}

function CriterionCard({ crit }: { crit: Criterion }) {
  const params = Object.entries(crit.resolvedParams ?? {});
  const defaulted = new Set(crit.defaultedParams ?? []);
  return (
    <div className="min-w-0 rounded-md border border-border bg-muted/20 p-2">
      <div className="flex items-start justify-between gap-2">
        <span className="min-w-0 break-all font-mono text-[11px] font-medium text-foreground">
          {crit.searchName != null && crit.searchName !== ""
            ? crit.searchName
            : "(unbound)"}
        </span>
        <StatusPill text={crit.role} />
      </div>
      <p className="mt-1 break-words text-[11px] leading-relaxed text-muted-foreground">
        {crit.text}
      </p>
      {params.length > 0 && (
        <div className="mt-1.5 space-y-0.5">
          {params.map(([key, value]) => (
            <div key={key} className="break-all font-mono text-[10px] leading-relaxed">
              <span className="text-muted-foreground">{key}</span>
              <span className="text-muted-foreground">: </span>
              <span className="text-foreground">{formatParamValue(value)}</span>
              {defaulted.has(key) && (
                <span
                  title="Assumed: the search's own default, not a value you stated"
                  className="ml-1 rounded-sm bg-warning/15 px-1 text-warning"
                >
                  assumed
                </span>
              )}
            </div>
          ))}
        </div>
      )}
      {(crit.openParams ?? []).map((slot) => (
        <p key={slot.paramName} className="mt-1 break-words text-[10px] text-warning">
          needs <span className="font-mono">{slot.paramName}</span>: {slot.question}
        </p>
      ))}
    </div>
  );
}

export function FrameDetail({ frame }: { frame: InvestigationLedger["frame"] }) {
  const spec = frame.spec;
  if (spec == null) return null;
  const { criteria = [], dropped = [] } = spec;
  return (
    <div className="mt-2 min-w-0 space-y-2 border-t border-border pt-2">
      <div className="space-y-1.5">
        {criteria.map((crit) => (
          <CriterionCard key={crit.id} crit={crit} />
        ))}
      </div>
      {frame.structureRender != null && frame.structureRender !== "" && (
        <div className="min-w-0 text-[10px]">
          <span className="text-muted-foreground">structure: </span>
          <span className="break-all font-mono text-foreground">
            {frame.structureRender}
          </span>
        </div>
      )}
      {dropped.length > 0 && (
        <div className="space-y-0.5">
          {dropped.map((d) => (
            <p key={d.text} className="break-words text-[10px] text-muted-foreground">
              <span className="text-destructive">dropped</span> {d.text} — {d.reason}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

const NODE_STATUS_TONE: Record<NodeResult["status"], Tone> = {
  ok: "good",
  zero: "warn",
  failed: "bad",
};

function NodeResultRow({ node }: { node: NodeResult }) {
  return (
    <div className="min-w-0 rounded-md border border-border bg-muted/20 p-2">
      <div className="flex items-start justify-between gap-2">
        <span className="min-w-0 break-all font-mono text-[11px] text-foreground">
          {node.searchName === "__combine__" ? "Combine" : node.searchName}
        </span>
        <div className="flex shrink-0 items-center gap-1.5">
          {node.count != null && (
            // A later edit moves the live count and not this one, so the
            // number says when it was true.
            <span className="font-mono text-[10px] text-muted-foreground">
              {node.count.toLocaleString()} genes at build
            </span>
          )}
          <StatusPill text={node.status} tone={NODE_STATUS_TONE[node.status]} />
        </div>
      </div>
      {node.error != null && node.error !== "" && (
        <p className="mt-1 break-words text-[10px] leading-relaxed text-destructive">
          {node.error}
        </p>
      )}
    </div>
  );
}

export function BuildDetail({ build }: { build: InvestigationLedger["build"] }) {
  const nodeResults = build.nodeResults;
  if (nodeResults.length === 0 && build.wdkUrl == null) return null;
  return (
    <div className="mt-2 min-w-0 space-y-2 border-t border-border pt-2">
      <div className="space-y-1.5">
        {nodeResults.map((node) => (
          <NodeResultRow key={node.nodeId} node={node} />
        ))}
      </div>
      {build.wdkUrl != null && (
        <a
          href={build.wdkUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-block break-all text-[10px] text-primary underline underline-offset-2"
        >
          Open strategy{build.wdkStrategyId != null ? ` #${build.wdkStrategyId}` : ""}
        </a>
      )}
    </div>
  );
}

function MarkdownList({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="min-w-0">
      <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <Markdown>{items.map((item) => `- ${item}`).join("\n")}</Markdown>
    </div>
  );
}

export function VerificationDetail({
  verification,
}: {
  verification: InvestigationLedger["verification"];
}) {
  const digest = verification.digest;
  if (digest == null) return null;
  return (
    <div className="mt-2 min-w-0 space-y-2 border-t border-border pt-2">
      {digest.prose !== "" && <Markdown>{digest.prose}</Markdown>}
      <MarkdownList label="key findings" items={digest.keyFindings ?? []} />
      <MarkdownList label="caveats" items={digest.caveats ?? []} />
    </div>
  );
}
