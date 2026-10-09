import * as React from "react";
import { flushSync } from "react-dom";
import { Tooltip as TooltipPrimitive } from "radix-ui";

import { cn } from "@/lib/utils/cn";

function TooltipProvider({
  delayDuration = 0,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Provider>) {
  return (
    <TooltipPrimitive.Provider
      data-slot="tooltip-provider"
      delayDuration={delayDuration}
      {...props}
    />
  );
}

type RootProps = Omit<
  React.ComponentProps<typeof TooltipPrimitive.Root>,
  "open" | "defaultOpen" | "onOpenChange"
>;

type TapState = {
  open: boolean;
  setOpen: (open: boolean) => void;
  holdOpenThroughClick: () => void;
};

const TapStateContext = React.createContext<TapState | null>(null);

function Tooltip({ tapToOpen = false, ...props }: RootProps & { tapToOpen?: boolean }) {
  if (tapToOpen) return <TapTooltip {...props} />;
  return <TooltipPrimitive.Root data-slot="tooltip" {...props} />;
}

function TapTooltip(props: RootProps) {
  const [open, setOpenState] = React.useState(false);
  const holdingRef = React.useRef(false);
  const setOpen = (next: boolean) => {
    if (!next && holdingRef.current) return;
    flushSync(() => setOpenState(next));
  };
  const holdOpenThroughClick = () => {
    holdingRef.current = true;
    queueMicrotask(() => {
      holdingRef.current = false;
    });
  };
  return (
    <TapStateContext value={{ open, setOpen, holdOpenThroughClick }}>
      <TooltipPrimitive.Root
        data-slot="tooltip"
        open={open}
        onOpenChange={setOpen}
        {...props}
      />
    </TapStateContext>
  );
}

type TriggerProps = React.ComponentProps<typeof TooltipPrimitive.Trigger>;

function TooltipTrigger(props: TriggerProps) {
  const tapState = React.use(TapStateContext);
  if (tapState === null) {
    return <TooltipPrimitive.Trigger data-slot="tooltip-trigger" {...props} />;
  }
  return <TapTrigger tapState={tapState} {...props} />;
}

function TapTrigger({
  tapState,
  onPointerDown,
  onPointerUp,
  onPointerCancel,
  onClick,
  ...props
}: TriggerProps & { tapState: TapState }) {
  const tapRef = React.useRef<"pending" | "opened" | null>(null);
  return (
    <TooltipPrimitive.Trigger
      data-slot="tooltip-trigger"
      onPointerDown={(event) => {
        tapRef.current =
          event.pointerType !== "mouse" && !tapState.open ? "pending" : null;
        onPointerDown?.(event);
      }}
      onPointerUp={(event) => {
        onPointerUp?.(event);
        if (tapRef.current !== "pending") return;
        tapRef.current = "opened";
        tapState.setOpen(true);
      }}
      onPointerCancel={(event) => {
        tapRef.current = null;
        onPointerCancel?.(event);
      }}
      onClick={(event) => {
        if (tapRef.current === "opened") tapState.holdOpenThroughClick();
        tapRef.current = null;
        onClick?.(event);
      }}
      {...props}
    />
  );
}

function TooltipContent({
  className,
  sideOffset = 0,
  children,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        data-slot="tooltip-content"
        sideOffset={sideOffset}
        className={cn(
          "z-50 w-fit origin-(--radix-tooltip-content-transform-origin) animate-in rounded-md bg-foreground px-3 py-1.5 text-xs text-balance text-background fade-in-0 zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
          className,
        )}
        {...props}
      >
        {children}
        <TooltipPrimitive.Arrow className="z-50 size-2.5 translate-y-[calc(-50%_-_2px)] rotate-45 rounded-[2px] bg-foreground fill-foreground" />
      </TooltipPrimitive.Content>
    </TooltipPrimitive.Portal>
  );
}

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider };
