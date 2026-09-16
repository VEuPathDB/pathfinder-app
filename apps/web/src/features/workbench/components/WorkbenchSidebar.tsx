"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useShallow } from "zustand/react/shallow";
import { useWorkbenchStore } from "@/state/useWorkbenchStore";
import { performSetOperation, createGeneSet } from "../api/geneSets";
import { useSessionStore } from "@/state/useSessionStore";
import { useGeneSetsQuery } from "@/features/workbench/hooks/useGeneSetsQuery";
import { useInvalidateGeneSets } from "@/features/workbench/hooks/useInvalidateGeneSets";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { GeneSetCard } from "./GeneSetCard";
import { GeneSetFilter } from "./GeneSetFilter";
import { geneSetLibraryState } from "./geneSetLibraryState";
import { SetVenn } from "@/features/workbench/components/SetVenn";
import { ComposeBar } from "./ComposeBar";
import { SelectionToolbar } from "./SelectionToolbar";
import { AddGeneSetModal } from "./AddGeneSetModal";
import { CompareModal } from "./CompareModal";
import { OverlapModal } from "./OverlapModal";

interface WorkbenchSidebarProps {
  onCollapse?: () => void;
}

export function WorkbenchSidebar({ onCollapse }: WorkbenchSidebarProps) {
  const router = useRouter();
  const selectedSite = useSessionStore((s) => s.selectedSite);
  const { data: geneSets = [], isFetched } = useGeneSetsQuery(selectedSite);
  const { data: authStatus } = useQuery(authStatusOptions(selectedSite));
  const invalidateGeneSets = useInvalidateGeneSets();
  const {
    activeSetId,
    selectedSetIds,
    setActiveSet,
    toggleSetSelection,
    clearSelection,
  } = useWorkbenchStore(
    useShallow((s) => ({
      activeSetId: s.activeSetId,
      selectedSetIds: s.selectedSetIds,
      setActiveSet: s.setActiveSet,
      toggleSetSelection: s.toggleSetSelection,
      clearSelection: s.clearSelection,
    })),
  );

  const [filter, setFilter] = useState("");
  const [showAddModal, setShowAddModal] = useState(false);
  const [showCompare, setShowCompare] = useState(false);
  const [showOverlap, setShowOverlap] = useState(false);
  const [composing, setComposing] = useState(false);

  // Derived state
  const activeSet = geneSets.find((gs) => gs.id === activeSetId) ?? null;
  // Order by selection, not the (newest-first) list, so set operations read
  // first-selected then second-selected (A − B uses the order the user picked).
  const selectedSets = selectedSetIds
    .map((id) => geneSets.find((gs) => gs.id === id))
    .filter((gs) => gs != null);
  const activeGeneIds = activeSet?.geneIds ?? [];

  const filterQuery = filter.trim().toLowerCase();
  const filteredSets = filterQuery
    ? geneSets.filter((gs) => gs.name.toLowerCase().includes(filterQuery))
    : geneSets;

  const libraryState = geneSetLibraryState({
    signedIn: authStatus?.signedIn === true,
    isFetched,
    count: geneSets.length,
  });
  const showFilter = geneSets.length >= 5;
  const showVenn = selectedSets.length >= 2 && selectedSets.length <= 5;
  const showCompose = selectedSets.length === 2;

  // -- Handlers ---------------------------------------------------------------

  const handleVennRegionClick = async (geneIds: string[], label: string) => {
    try {
      const gs = await createGeneSet({
        name: label,
        source: "derived",
        geneIds,
        siteId: selectedSite,
      });
      await invalidateGeneSets();
      setActiveSet(gs.id);
      router.push(`/${selectedSite}/workbench/${gs.id}`);
    } catch (err) {
      console.error("Failed to create set from Venn region:", err);
    }
  };

  const handleComposeExecute = async (result: {
    operation: string;
    geneIds: string[];
    name: string;
  }) => {
    const setA = selectedSets[0];
    const setB = selectedSets[1];
    if (selectedSets.length !== 2 || setA == null || setB == null) return;
    setComposing(true);
    try {
      const gs = await performSetOperation({
        operation: result.operation as "intersect" | "union" | "minus",
        setAId: setA.id,
        setBId: setB.id,
        name: result.name,
      });
      await invalidateGeneSets();
      setActiveSet(gs.id);
      router.push(`/${selectedSite}/workbench/${gs.id}`);
      clearSelection();
    } catch (err) {
      console.error("Failed to execute set operation:", err);
    } finally {
      setComposing(false);
    }
  };

  return (
    <TooltipProvider delayDuration={300}>
      <aside className="flex h-full flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-3 pt-4 pb-2">
          <div className="flex items-center gap-1">
            {onCollapse && (
              <button
                type="button"
                onClick={onCollapse}
                aria-label="Collapse sidebar"
                className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </button>
            )}
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Gene Sets
            </h3>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowAddModal(true)}
            className="h-7 gap-1 px-2 text-xs"
          >
            <Plus className="h-3.5 w-3.5" />
            Add
          </Button>
        </div>

        {/* Filter (shown at 5+ sets) */}
        {showFilter && (
          <div className="px-3 pb-2">
            <GeneSetFilter value={filter} onChange={setFilter} />
          </div>
        )}

        {/* Zone 1: Library (scrollable list) */}
        <ScrollArea className="flex-1 px-3">
          {libraryState === "signed-out" ? (
            <p className="px-1 py-4 text-xs text-muted-foreground">
              Sign in to VEuPathDB to see your gene sets.
            </p>
          ) : libraryState === "loading" ? (
            <p className="px-1 py-4 text-xs text-muted-foreground">
              Loading your gene sets...
            </p>
          ) : libraryState === "empty" ? (
            <p className="px-1 py-4 text-xs text-muted-foreground">
              No gene sets yet. Click <strong>Add</strong> to get started.
            </p>
          ) : filteredSets.length === 0 ? (
            <p className="px-1 py-4 text-xs text-muted-foreground">
              No gene sets match &quot;{filter}&quot;
            </p>
          ) : (
            <div className="flex flex-col gap-0.5 pb-2">
              {filteredSets.map((gs) => (
                <GeneSetCard
                  key={gs.id}
                  geneSet={gs}
                  isActive={activeSetId === gs.id}
                  isSelected={selectedSetIds.includes(gs.id)}
                  activeGeneIds={activeGeneIds}
                  onActivate={() => {
                    setActiveSet(gs.id);
                    router.push(`/${selectedSite}/workbench/${gs.id}`);
                  }}
                  onToggleSelect={() => toggleSetSelection(gs.id)}
                />
              ))}
            </div>
          )}
        </ScrollArea>

        {/* Zone 2: Live Venn (when 2-5 selected) */}
        {showVenn && (
          <div className="border-t border-border px-3 py-3">
            <SetVenn
              sets={selectedSets.map((s) => ({
                key: s.name,
                geneIds: s.geneIds,
              }))}
              onRegionClick={(geneIds, label) => {
                void handleVennRegionClick(geneIds, label);
              }}
              height={selectedSets.length > 3 ? 280 : 200}
              width={240}
            />
          </div>
        )}

        {/* Zone 3: Compose (when 2 selected) */}
        {showCompose && selectedSets[0] != null && selectedSets[1] != null && (
          <div className="border-t border-border px-3 py-3">
            <ComposeBar
              setA={selectedSets[0]}
              setB={selectedSets[1]}
              onExecute={(result) => {
                void handleComposeExecute(result);
              }}
              loading={composing}
            />
          </div>
        )}

        {/* Bottom toolbar (always) */}
        <SelectionToolbar
          activeSet={activeSet}
          selectedSets={selectedSets}
          allSetIds={geneSets.map((gs) => gs.id)}
          onCompare={() => setShowCompare(true)}
          onOverlap={() => setShowOverlap(true)}
        />

        {/* Modals */}
        <AddGeneSetModal open={showAddModal} onClose={() => setShowAddModal(false)} />

        {showCompare &&
          selectedSets.length === 2 &&
          selectedSets[0] != null &&
          selectedSets[1] != null && (
            <CompareModal
              open={showCompare}
              onClose={() => setShowCompare(false)}
              setA={selectedSets[0]}
              setB={selectedSets[1]}
            />
          )}

        {showOverlap && selectedSets.length >= 2 && (
          <OverlapModal
            open={showOverlap}
            onClose={() => setShowOverlap(false)}
            sets={selectedSets}
          />
        )}
      </aside>
    </TooltipProvider>
  );
}
