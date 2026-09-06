import type { EntityRef } from "@/features/workbench/analysis/api/stepResults";
import { useAttributeFiltering } from "@/features/workbench/analysis/hooks/useAttributeFiltering";
import { QueryBoundary } from "@/lib/components/QueryBoundary";
import { DistributionSection } from "./DistributionSection";

interface DistributionExplorerProps {
  entityRef: EntityRef;
}

export function DistributionExplorer({ entityRef }: DistributionExplorerProps) {
  return (
    <QueryBoundary>
      <DistributionExplorerContent entityRef={entityRef} />
    </QueryBoundary>
  );
}

function DistributionExplorerContent({ entityRef }: DistributionExplorerProps) {
  const { attributes, selectedAttr, setSelectedAttr } =
    useAttributeFiltering(entityRef);

  if (attributes.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        No attributes with distribution data found.
      </div>
    );
  }

  if (selectedAttr === "") return null;

  return (
    <div className="space-y-4">
      <QueryBoundary>
        <DistributionSection
          entityRef={entityRef}
          selectedAttr={selectedAttr}
          attributes={attributes}
          onSelectAttr={setSelectedAttr}
        />
      </QueryBoundary>
    </div>
  );
}
