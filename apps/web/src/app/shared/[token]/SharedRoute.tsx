"use client";

import { useParams } from "next/navigation";

import { useSitePages } from "@/app/hooks/useSitePages";
import { SharedConversationView } from "@/features/conversation/shared/SharedConversationView";

export function SharedRoute() {
  const { token } = useParams<{ token: string }>();
  const { signInUrl } = useSitePages();
  return <SharedConversationView token={token} signInUrl={signInUrl} />;
}
