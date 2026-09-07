import { redirectToEntrySite } from "@/app/entrySiteRedirect";
import { chatRoot } from "@/lib/routes";

export const dynamic = "force-dynamic";

export default async function BareConversationPage() {
  return await redirectToEntrySite(chatRoot);
}
