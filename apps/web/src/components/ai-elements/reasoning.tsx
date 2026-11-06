"use client";

import { useControllableState } from "@radix-ui/react-use-controllable-state";
import { Collapsible, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils/cn";
import { cjk } from "@streamdown/cjk";
import { code } from "@streamdown/code";
import { math } from "@streamdown/math";

import { modelMarkdownComponents } from "@/lib/markdown/modelImage";
import { mermaid } from "@streamdown/mermaid";
import { ChevronDownIcon } from "lucide-react";
import type { ComponentProps, HTMLAttributes, ReactNode } from "react";
import {
  createContext,
  memo,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { Streamdown } from "streamdown";
import { Shimmer } from "./shimmer";

type ReasoningContextValue = {
  isStreaming: boolean;
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
  duration: number | undefined;
};

const ReasoningContext = createContext<ReasoningContextValue | null>(null);

export const useReasoning = () => {
  const context = useContext(ReasoningContext);
  if (!context) {
    throw new Error("Reasoning components must be used within Reasoning");
  }
  return context;
};

export type ReasoningProps = ComponentProps<typeof Collapsible> & {
  isStreaming?: boolean;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  duration?: number;
};

const AUTO_CLOSE_DELAY = 1000;
const MS_IN_S = 1000;

export const Reasoning = memo(
  ({
    className,
    isStreaming = false,
    open,
    defaultOpen,
    onOpenChange,
    duration: durationProp,
    children,
    ...props
  }: ReasoningProps) => {
    const resolvedDefaultOpen = defaultOpen ?? isStreaming;
    const isExplicitlyClosed = defaultOpen === false;

    const [isOpen, setIsOpen] = useControllableState<boolean>({
      defaultProp: resolvedDefaultOpen,
      prop: open,
      ...(onOpenChange !== undefined && { onChange: onOpenChange }),
    });
    const [duration, setDuration] = useControllableState<number | undefined>({
      defaultProp: undefined,
      prop: durationProp,
    });

    const hasEverStreamedRef = useRef(isStreaming);
    const [hasAutoClosed, setHasAutoClosed] = useState(false);
    const startTimeRef = useRef<number | null>(null);

    useEffect(() => {
      if (isStreaming) {
        hasEverStreamedRef.current = true;
        if (startTimeRef.current === null) {
          startTimeRef.current = Date.now();
        }
      } else if (startTimeRef.current !== null) {
        setDuration(Math.ceil((Date.now() - startTimeRef.current) / MS_IN_S));
        startTimeRef.current = null;
      }
    }, [isStreaming, setDuration]);

    useEffect(() => {
      if (isStreaming && !isOpen && !isExplicitlyClosed) {
        setIsOpen(true);
      }
    }, [isStreaming, isOpen, setIsOpen, isExplicitlyClosed]);

    useEffect(() => {
      if (hasEverStreamedRef.current && !isStreaming && isOpen && !hasAutoClosed) {
        const timer = setTimeout(() => {
          setIsOpen(false);
          setHasAutoClosed(true);
        }, AUTO_CLOSE_DELAY);
        return () => clearTimeout(timer);
      }
      return undefined;
    }, [isStreaming, isOpen, setIsOpen, hasAutoClosed]);

    const handleOpenChange = useCallback(
      (newOpen: boolean) => {
        setIsOpen(newOpen);
      },
      [setIsOpen],
    );

    const contextValue = useMemo(
      () => ({ duration, isOpen, isStreaming, setIsOpen }),
      [duration, isOpen, isStreaming, setIsOpen],
    );

    return (
      <ReasoningContext.Provider value={contextValue}>
        <Collapsible
          className={cn("not-prose", className)}
          onOpenChange={handleOpenChange}
          open={isOpen}
          {...props}
        >
          {children}
        </Collapsible>
      </ReasoningContext.Provider>
    );
  },
);

export type ReasoningTriggerProps = ComponentProps<typeof CollapsibleTrigger> & {
  getThinkingMessage?: (isStreaming: boolean, duration?: number) => ReactNode;
};

const defaultGetThinkingMessage = (isStreaming: boolean, duration?: number) => {
  if (isStreaming || duration === 0) {
    return (
      <Shimmer className="font-medium" duration={1}>
        Thinking...
      </Shimmer>
    );
  }
  if (duration === undefined) {
    return <p>Thought for a few seconds</p>;
  }
  return <p>Thought for {duration} seconds</p>;
};

export const ReasoningTrigger = memo(
  ({
    className,
    children,
    getThinkingMessage = defaultGetThinkingMessage,
    ...props
  }: ReasoningTriggerProps) => {
    const { isStreaming, isOpen, duration } = useReasoning();

    return (
      <CollapsibleTrigger
        data-testid="reasoning-trigger"
        className={cn(
          "flex w-full items-center gap-2 text-muted-foreground text-[0.8125rem] leading-[1.65] transition-colors hover:text-foreground",
          className,
        )}
        {...props}
      >
        {children ?? (
          <>
            {getThinkingMessage(isStreaming, duration)}
            <ChevronDownIcon
              className={cn(
                "size-4 transition-transform",
                isOpen ? "rotate-180" : "rotate-0",
              )}
            />
          </>
        )}
      </CollapsibleTrigger>
    );
  },
);

export type ReasoningContentProps = HTMLAttributes<HTMLDivElement> & {
  children: string;
};

const streamdownPlugins = { cjk, code, math, mermaid };

export const ReasoningContent = memo(
  ({ className, children }: ReasoningContentProps) => {
    const { isStreaming, isOpen } = useReasoning();
    const scrollRef = useRef<HTMLDivElement>(null);
    const scrollId = useId();
    const [expanded, setExpanded] = useState(false);
    useEffect(() => {
      if (isStreaming && scrollRef.current !== null) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    }, [children, isStreaming]);

    if (!isOpen) return null;

    return (
      <div
        className={cn(
          "mt-2 animate-in fade-in-0 duration-200 text-muted-foreground [overflow-anchor:none]",
          className,
        )}
      >
        <div
          id={scrollId}
          data-testid="reasoning-scroll"
          className={cn(
            "rounded-lg border border-border/20 bg-muted/30 px-3 py-2 text-[0.6875rem] leading-relaxed",
            !expanded && "max-h-[12.5rem] overflow-y-auto",
          )}
          ref={scrollRef}
        >
          <Streamdown plugins={streamdownPlugins} components={modelMarkdownComponents}>
            {children}
          </Streamdown>
        </div>
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={scrollId}
          onClick={() => setExpanded(!expanded)}
          className="mt-1 rounded-sm px-1 text-xs font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
        >
          {expanded ? "Show less" : "Show all"}
        </button>
      </div>
    );
  },
);

Reasoning.displayName = "Reasoning";
ReasoningTrigger.displayName = "ReasoningTrigger";
ReasoningContent.displayName = "ReasoningContent";
