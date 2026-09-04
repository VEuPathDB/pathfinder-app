"use client";

import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryProvider } from "@/lib/query/QueryProvider";
import { NuqsProvider } from "@/app/providers/NuqsProvider";
import { SonnerProvider } from "@/app/providers/SonnerProvider";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <NuqsProvider>
      <QueryProvider>
        <TooltipProvider delayDuration={300}>{children}</TooltipProvider>
        <SonnerProvider />
      </QueryProvider>
    </NuqsProvider>
  );
}
