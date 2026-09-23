"use client";

import { Loader2, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useTimeout } from "usehooks-ts";

import { Button } from "@/components/ui/button";
import { reloadPage } from "./reloadPage";
import { STARTUP_GRACE_MS } from "./StartupScreen";

/** Offers a page reload once loading outlasts the startup grace window. */
export function LoadingScreen() {
  const [stalled, setStalled] = useState(false);
  useTimeout(() => setStalled(true), STARTUP_GRACE_MS);

  return (
    <div className="flex h-full flex-col items-center justify-center bg-background text-foreground">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      <p className="mt-3 text-sm text-muted-foreground">Loading...</p>
      {stalled && (
        <>
          <p className="mt-1 text-xs text-muted-foreground">
            This is taking longer than usual.
          </p>
          <Button
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={() => reloadPage()}
          >
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
            Reload
          </Button>
        </>
      )}
    </div>
  );
}
