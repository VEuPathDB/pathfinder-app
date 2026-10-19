import { redirectToEntrySite } from "@/app/entrySiteRedirect";

export const dynamic = "force-dynamic";

export default async function BareConversationPage() {
  return await redirectToEntrySite();
}
