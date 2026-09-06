import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { ClassifiedRecord } from "@pathfinder/shared/generated/types/ClassifiedRecord";
import {
  getRecords,
  type EntityRef,
} from "@/features/workbench/analysis/api/stepResults";

interface DistributionModalState {
  modalValue: string | null;
  modalRecords: ClassifiedRecord[];
  loadingModal: boolean;
  handleBarClick: (value: string) => void;
  closeModal: () => void;
}

export function useDistributionModal(
  entityRef: EntityRef,
  selectedAttr: string,
): DistributionModalState {
  const [modalValue, setModalValue] = useState<string | null>(null);

  const { data, isPending } = useQuery({
    queryKey: [
      "experiments",
      "records",
      entityRef.type,
      entityRef.id,
      {
        modal: true,
        filterAttribute: selectedAttr,
        filterValue: modalValue,
      },
    ] as const,
    queryFn: () =>
      getRecords(entityRef, {
        attributes: [selectedAttr, "gene_product"],
        filterAttribute: selectedAttr,
        filterValue: modalValue!,
        limit: 500,
      }),
    enabled: modalValue != null,
    staleTime: 60_000,
  });

  const handleBarClick = (value: string) => {
    setModalValue(value);
  };

  const closeModal = () => setModalValue(null);

  return {
    modalValue,
    modalRecords: data?.records ?? [],
    loadingModal: isPending && modalValue != null,
    handleBarClick,
    closeModal,
  };
}
