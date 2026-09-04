import Image from "next/image";
import { RefreshCw, ServerOff } from "lucide-react";
import { Button } from "@/components/ui/button";

interface SetupRequiredScreenProps {
  onRetry: () => void;
}

export function SetupRequiredScreen({ onRetry }: SetupRequiredScreenProps) {
  return (
    <div className="flex h-full flex-col items-center justify-center bg-background px-6 text-foreground">
      <div className="w-full max-w-md space-y-6 text-center">
        <div className="flex flex-col items-center gap-3">
          <Image src="/pathfinder.svg" alt="" width={48} height={48} />
          <ServerOff className="h-10 w-10 text-muted-foreground" />
        </div>

        <div>
          <h1 className="text-lg font-semibold">Setup Required</h1>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            PathFinder could not find a configured model backend for this runtime
            profile.
          </p>
        </div>

        <div className="rounded-lg border border-border bg-muted/50 px-4 py-3 text-left text-xs leading-relaxed text-muted-foreground">
          <p className="mb-2 font-medium text-foreground">
            Set at least one of the following in your{" "}
            <code className="rounded bg-muted px-1 py-0.5">.env</code> file:
          </p>
          <ul className="list-inside list-disc space-y-1 font-mono">
            <li>OPENAI_API_KEY</li>
            <li>ANTHROPIC_API_KEY</li>
            <li>GEMINI_API_KEY</li>
            <li>OLLAMA_BASE_URL (local models)</li>
          </ul>
          <p className="mt-2">
            For test harnesses only, set{" "}
            <code className="rounded bg-muted px-1 py-0.5">
              PATHFINDER_CHAT_PROVIDER=mock
            </code>{" "}
            in the test profile to run without a real LLM.
          </p>
        </div>

        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          Re-check
        </Button>
      </div>
    </div>
  );
}
