import { redirectToEntrySite } from "@/app/entrySiteRedirect";
import { workbenchRoot } from "@/lib/routes";

export const dynamic = "force-dynamic";

export default async function BareWorkbenchPage() {
  return await redirectToEntrySite(workbenchRoot);
}
