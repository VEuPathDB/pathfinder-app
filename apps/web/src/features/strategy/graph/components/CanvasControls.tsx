"use client";

import { LayoutGrid, Maximize2, Minus, Plus } from "lucide-react";
import { useReactFlow } from "@xyflow/react";
import { Button } from "@/components/ui/button";
import { ButtonGroup, ButtonGroupSeparator } from "@/components/ui/button-group";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface CanvasControlsProps {
  onRelayout: () => void;
}

export function CanvasControls({ onRelayout }: CanvasControlsProps) {
  const { fitView, zoomIn, zoomOut } = useReactFlow();

  return (
    <TooltipProvider delayDuration={150}>
      <ButtonGroup
        aria-label="Canvas controls"
        data-testid="canvas-controls"
        className="rounded-md border border-border bg-background shadow-sm"
      >
        <ControlButton
          label="Tidy layout (R)"
          ariaLabel="Tidy layout"
          onClick={onRelayout}
          icon={<LayoutGrid className="size-4" />}
        />
        <ControlButton
          label="Fit to view (F)"
          ariaLabel="Fit to view"
          onClick={() => void fitView({ padding: 0.3, duration: 300 })}
          icon={<Maximize2 className="size-4" />}
        />
        <ButtonGroupSeparator />
        <ControlButton
          label="Zoom in (+)"
          ariaLabel="Zoom in"
          onClick={() => void zoomIn({ duration: 150 })}
          icon={<Plus className="size-4" />}
        />
        <ControlButton
          label="Zoom out (−)"
          ariaLabel="Zoom out"
          onClick={() => void zoomOut({ duration: 150 })}
          icon={<Minus className="size-4" />}
        />
      </ButtonGroup>
    </TooltipProvider>
  );
}

interface ControlButtonProps {
  label: string;
  ariaLabel: string;
  onClick: () => void;
  icon: React.ReactNode;
}

function ControlButton({ label, ariaLabel, onClick, icon }: ControlButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={onClick}
          aria-label={ariaLabel}
        >
          {icon}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="top">{label}</TooltipContent>
    </Tooltip>
  );
}
