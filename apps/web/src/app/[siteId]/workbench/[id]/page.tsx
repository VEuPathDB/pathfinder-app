"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useWorkbenchStore } from "@/state/useWorkbenchStore";
import { useSessionStore } from "@/state/useSessionStore";
import { useGeneSetsQuery } from "@/features/workbench/hooks/useGeneSetsQuery";
import { WorkbenchMain } from "@/features/workbench/components/WorkbenchMain";

export default function WorkbenchGeneSetPage() {
  const { id } = useParams<{ id: string }>();
  const setActiveSet = useWorkbenchStore((s) => s.setActiveSet);
  const selectedSite = useSessionStore((s) => s.selectedSite);
  const { data: geneSets = [] } = useGeneSetsQuery(selectedSite);

  const geneSetExists = geneSets.some((gs) => gs.id === id);
  const [prevActivated, setPrevActivated] = useState<string | null>(null);
  if (id && geneSetExists && prevActivated !== id) {
    setPrevActivated(id);
    setActiveSet(id);
  }

  return <WorkbenchMain />;
}
