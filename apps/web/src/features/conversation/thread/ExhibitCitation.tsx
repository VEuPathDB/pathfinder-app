"use client";

import { Link2 } from "lucide-react";
import { toast } from "sonner";
import type { ReactElement } from "react";

import { Button } from "@/components/ui/button";

import { exhibitAnchorId, exhibitLabel, type ExhibitKind } from "./exhibits";

interface ExhibitCitationProps {
  kind: ExhibitKind;
  number: number;
}

/** Copies this conversation's url with the exhibit's fragment, so the exhibit
 * can be cited on its own. */
export function ExhibitCitation({ kind, number }: ExhibitCitationProps): ReactElement {
  const label = exhibitLabel(kind, number);
  const copy = () => {
    const { origin, pathname } = window.location;
    void navigator.clipboard.writeText(
      `${origin}${pathname}#${exhibitAnchorId(kind, number)}`,
    );
    toast.success(`Link to ${label} copied`);
  };
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-xs"
      data-testid="exhibit-citation"
      aria-label={`Copy link to ${label}`}
      onClick={copy}
    >
      <Link2 className="size-3" aria-hidden />
    </Button>
  );
}
