import { currentWebBuild } from "@/lib/webBuild";

export const dynamic = "force-dynamic";

export function GET(): Response {
  return Response.json(
    { build: currentWebBuild() },
    { headers: { "Cache-Control": "no-store" } },
  );
}
