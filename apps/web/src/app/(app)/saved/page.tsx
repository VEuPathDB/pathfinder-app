"use client";

import { useCurrentSite } from "@/app/hooks/useCurrentSite";
import { SavedStrategiesPage } from "@/features/saved/SavedStrategiesPage";

export default function Page() {
  const { siteId } = useCurrentSite();
  return <SavedStrategiesPage siteId={siteId} />;
}
