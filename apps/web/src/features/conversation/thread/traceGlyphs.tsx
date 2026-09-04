import {
  Ban,
  Check,
  CircleDashed,
  CircleSlash,
  Loader2,
  ShieldAlert,
  TriangleAlert,
  X,
  type LucideIcon,
} from "lucide-react";
import type { TraceRowStatus } from "@pathfinder/assistant-client";

export interface TraceGlyph {
  Icon: LucideIcon;
  className: string;
}

/**
 * One glyph per row status. A call that found nothing and a call that found
 * something never read the same, so the silent zero stays visible.
 */
export const TRACE_GLYPHS: Record<TraceRowStatus, TraceGlyph> = {
  running: { Icon: Loader2, className: "animate-spin text-muted-foreground" },
  ok: { Icon: Check, className: "text-success" },
  empty: { Icon: CircleSlash, className: "text-warning" },
  warn: { Icon: TriangleAlert, className: "text-warning" },
  error: { Icon: X, className: "text-destructive" },
  denied: { Icon: Ban, className: "text-muted-foreground" },
  "awaiting-approval": { Icon: ShieldAlert, className: "text-warning" },
  stopped: { Icon: CircleDashed, className: "text-muted-foreground" },
};
