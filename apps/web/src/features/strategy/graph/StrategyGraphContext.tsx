"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { Strategy } from "@strategist/shared";
import type { useStrategyGraph } from "@/features/strategy/graph/hooks/useStrategyGraph";

export type StrategyGraphContextValue = ReturnType<typeof useStrategyGraph> & {
  strategy: Strategy | null;
  siteId: string;
};

const Ctx = createContext<StrategyGraphContextValue | null>(null);

export function StrategyGraphProvider({
  value,
  children,
}: {
  value: StrategyGraphContextValue;
  children: ReactNode;
}) {
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useStrategyGraphCtx(): StrategyGraphContextValue {
  const ctx = useContext(Ctx);
  if (!ctx) {
    throw new Error("useStrategyGraphCtx must be used within StrategyGraphProvider");
  }
  return ctx;
}
