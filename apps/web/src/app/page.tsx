import { redirectToEntrySite } from "@/app/entrySiteRedirect";

export const dynamic = "force-dynamic";

export default async function RootPage() {
  return await redirectToEntrySite();
}
