"use client";

import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, RefreshCw } from "lucide-react";
import type { FallbackProps } from "react-error-boundary";
import { Button } from "@/components/ui/button";

export function DefaultQueryError({ error, resetErrorBoundary }: FallbackProps) {
  const queryClient = useQueryClient();

  function handleRetry() {
    void queryClient.resetQueries({ predicate: (q) => q.state.status === "error" });
    resetErrorBoundary();
  }

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-4">
      <AlertTriangle className="h-6 w-6 text-destructive" />
      <p className="text-sm text-muted-foreground">
        {error instanceof Error ? error.message : "Something went wrong"}
      </p>
      <Button variant="outline" size="sm" onClick={handleRetry}>
        <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
        Retry
      </Button>
    </div>
  );
}
