import { redirectToEntrySite } from "@/app/entrySiteRedirect";
import { workbenchGeneSetUrl } from "@/lib/routes";

export const dynamic = "force-dynamic";

export default async function BareWorkbenchItemPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return await redirectToEntrySite((siteId) => workbenchGeneSetUrl(siteId, id));
}
