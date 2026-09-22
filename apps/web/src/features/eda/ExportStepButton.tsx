"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { Strategy } from "@pathfinder/shared";

import { Button } from "@/components/ui/button";
import { patchConversationEda } from "@/features/eda/api";
import { toUserMessage } from "@/lib/api/errors";
import { writeStrategy } from "@/lib/api/strategy";
import { strategyCanvasUrl } from "@/lib/routes";
import { isEdaJobComplete, useEdaStore } from "@/state/eda";

import {
  exportedStepPlacement,
  strategyFromExportedStep,
  type ExportedStepPlacement,
} from "./exportedStep";

const EXPORT_FAILED = "Export failed";
const LINK_CLASS = "underline underline-offset-2";

interface ExportOutcome {
  strategy: Strategy;
  placement: ExportedStepPlacement;
}

export function ExportStepButton({ conversationId }: { conversationId: string }) {
  const queryClient = useQueryClient();
  const jobs = useEdaStore((s) => s.jobs);
  const thresholds = useEdaStore((s) => s.volcanoThresholds);
  const analysis = useEdaStore((s) => s.analysis);
  const applyAnalysisState = useEdaStore((s) => s.applyAnalysisState);
  const canExportRows = analysis?.canExportRows === true;
  const siteId = analysis?.siteId ?? "";
  const computeComplete = Object.values(jobs).some(isEdaJobComplete);

  const exportStep = useMutation({
    mutationFn: async (): Promise<ExportOutcome> => {
      const response = await patchConversationEda(conversationId, {
        action: "export-step",
        thresholds: {
          effectSizeThreshold: thresholds.effectSizeThreshold,
          significanceThreshold: thresholds.significanceThreshold,
          effectDirection: thresholds.direction,
        },
      });
      if (response.analysis !== null) applyAnalysisState(response.analysis);
      const strategy = strategyFromExportedStep(response.step);
      return { strategy, placement: exportedStepPlacement(strategy) };
    },
    onSuccess: ({ strategy }) => {
      writeStrategy(queryClient, conversationId, strategy);
    },
    onError: (error) => toast.error(toUserMessage(error, EXPORT_FAILED)),
  });

  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        type="button"
        size="sm"
        disabled={!computeComplete || !canExportRows || exportStep.isPending}
        onClick={() => exportStep.mutate()}
      >
        Export as step
      </Button>
      {!canExportRows ? (
        <p
          data-testid="eda-export-blocked"
          className="text-[11px] text-muted-foreground"
        >
          This study cannot export genes as a step.
        </p>
      ) : null}
      {exportStep.data !== undefined ? (
        <PlacementNotice
          placement={exportStep.data.placement}
          href={strategyCanvasUrl(siteId, conversationId)}
        />
      ) : null}
      {exportStep.error !== null ? (
        <p data-testid="eda-export-error" className="text-[11px] text-destructive">
          {toUserMessage(exportStep.error, EXPORT_FAILED)}
        </p>
      ) : null}
    </div>
  );
}

function PlacementNotice({
  placement,
  href,
}: {
  placement: ExportedStepPlacement;
  href: string;
}) {
  if (placement.kind === "begins-strategy") {
    return (
      <p
        data-testid="eda-export-began-strategy"
        className="text-[11px] text-muted-foreground"
      >
        {"This step is now the strategy's first step. "}
        <a href={href} className={LINK_CLASS}>
          Open the strategy canvas
        </a>
      </p>
    );
  }
  return (
    <p
      data-testid="eda-export-draft-step"
      className="text-[11px] text-muted-foreground"
    >
      {
        "This step is a draft root. It is not part of the pushed strategy until you attach it. "
      }
      <a href={href} className={LINK_CLASS}>
        Attach it in the strategy canvas
      </a>
    </p>
  );
}
