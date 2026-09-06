import { AlertCircle } from "lucide-react";
import type { EntityRef } from "@/features/workbench/analysis/api/stepResults";
import type { RecordAttribute } from "@pathfinder/shared/generated/types/RecordAttribute";
import { useDistributionData } from "@/features/workbench/analysis/hooks/useDistributionData";
import { useDistributionModal } from "@/features/workbench/analysis/hooks/useDistributionModal";
import { AttributeSelector } from "./AttributeSelector";
import { DistributionChart } from "./DistributionChart";

interface DistributionSectionProps {
  entityRef: EntityRef;
  selectedAttr: string;
  attributes: RecordAttribute[];
  onSelectAttr: (attr: string) => void;
}

export function DistributionSection({
  entityRef,
  selectedAttr,
  attributes,
  onSelectAttr,
}: DistributionSectionProps) {
  const dist = useDistributionData(entityRef, selectedAttr);
  const modal = useDistributionModal(entityRef, selectedAttr);

  return (
    <>
      <AttributeSelector
        attributes={attributes}
        selectedAttr={selectedAttr}
        onSelect={onSelectAttr}
        onRefresh={dist.refresh}
        refreshing={false}
      />

      {dist.noData && (
        <div className="flex items-center gap-2 text-xs text-destructive">
          <AlertCircle className="h-3.5 w-3.5" />
          No distribution data available for this attribute. Try a different one.
        </div>
      )}

      <DistributionChart
        distribution={dist.distribution}
        loading={false}
        selectedAttr={selectedAttr}
        attributes={attributes}
        modalValue={modal.modalValue}
        modalRecords={modal.modalRecords}
        loadingModal={modal.loadingModal}
        onBarClick={modal.handleBarClick}
        onCloseModal={modal.closeModal}
      />
    </>
  );
}
