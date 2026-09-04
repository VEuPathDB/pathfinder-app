"use client";

import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { Card } from "@/components/ui/card";
import { useWorkbenchStore } from "@/state/useWorkbenchStore";
import type { PanelId } from "@/state/useWorkbenchStore";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface AnalysisPanelContainerProps {
  panelId: PanelId;
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  disabled?: boolean;
  disabledReason?: string;
  children: React.ReactNode;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function AnalysisPanelContainer({
  panelId,
  title,
  subtitle,
  icon,
  disabled = false,
  disabledReason,
  children,
}: AnalysisPanelContainerProps) {
  const expanded = useWorkbenchStore((s) => s.expandedPanels.has(panelId));
  const togglePanel = useWorkbenchStore((s) => s.togglePanel);

  const handleToggle = () => {
    if (disabled) return;
    togglePanel(panelId);
  };

  const isExpanded = expanded && !disabled;
  const displaySubtitle = disabled ? (disabledReason ?? subtitle) : subtitle;

  return (
    <Card>
      {/* ---- Header ---- */}
      <button
        type="button"
        onClick={handleToggle}
        disabled={disabled}
        aria-expanded={isExpanded}
        className={cn(
          "flex w-full items-center gap-3 px-4 py-3 text-left transition-colors duration-150",
          disabled
            ? "cursor-not-allowed opacity-50"
            : "cursor-pointer hover:bg-accent/50",
        )}
      >
        {/* Chevron */}
        <ChevronRight
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200",
            isExpanded && "rotate-90",
          )}
          aria-hidden="true"
        />

        {/* Icon */}
        {icon != null && (
          <span className="shrink-0 text-muted-foreground" aria-hidden="true">
            {icon}
          </span>
        )}

        {/* Title & subtitle */}
        <div className="min-w-0 flex-1">
          <span className="block text-sm font-medium text-foreground">{title}</span>
          {displaySubtitle != null && displaySubtitle !== "" && (
            <span className="block truncate text-xs text-muted-foreground">
              {displaySubtitle}
            </span>
          )}
        </div>
      </button>

      {/* ---- Content ---- */}
      {isExpanded && (
        <div className="overflow-hidden border-t animate-panel-expand">
          <div className="px-4 py-4">{children}</div>
        </div>
      )}
    </Card>
  );
}
