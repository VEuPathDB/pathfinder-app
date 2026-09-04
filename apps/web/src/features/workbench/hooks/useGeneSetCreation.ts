"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import type { ResolvedGene } from "@pathfinder/shared";
import { resolveGenes } from "@pathfinder/shared/generated/hooks/useResolveGenes";
import { createGeneSet } from "../api/geneSets";
import { useSessionStore } from "@/state/useSessionStore";
import { useInvalidateGeneSets } from "@/features/workbench/hooks/useInvalidateGeneSets";

interface UseGeneSetCreationOptions {
  onCreated: () => void;
}

export function useGeneSetCreation({ onCreated }: UseGeneSetCreationOptions) {
  const selectedSite = useSessionStore((s) => s.selectedSite);
  const invalidateGeneSets = useInvalidateGeneSets();

  const [error, setError] = useState<string | null>(null);
  const [verificationState, setVerificationState] = useState<{
    verified: boolean;
    resolvedGenes: ResolvedGene[] | null;
    unresolvedIds: string[];
  }>({
    verified: false,
    resolvedGenes: null,
    unresolvedIds: [],
  });

  const verifyMutation = useMutation({
    mutationFn: (parsedIds: string[]) =>
      resolveGenes(selectedSite, { geneIds: parsedIds }),
    onSuccess: (data) => {
      setVerificationState({
        verified: true,
        resolvedGenes: data.resolved,
        unresolvedIds: data.unresolved,
      });
    },
    onError: (err: Error) => {
      setError(err.message);
      setVerificationState({
        verified: false,
        resolvedGenes: null,
        unresolvedIds: [],
      });
    },
    onMutate: () => {
      setError(null);
      setVerificationState({
        verified: false,
        resolvedGenes: null,
        unresolvedIds: [],
      });
    },
  });

  const createMutation = useMutation({
    mutationFn: (args: {
      name: string;
      geneIds: string[];
      source: "paste" | "upload";
    }) =>
      createGeneSet({
        name: args.name,
        source: args.source,
        geneIds: args.geneIds,
        siteId: selectedSite,
      }),
    onSuccess: async () => {
      await invalidateGeneSets();
      onCreated();
    },
    onError: (err: Error) => {
      setError(err.message);
    },
    onMutate: () => {
      setError(null);
    },
  });

  const { verified, resolvedGenes, unresolvedIds } = verificationState;

  const resetVerification = () => {
    verifyMutation.reset();
    setVerificationState({
      verified: false,
      resolvedGenes: null,
      unresolvedIds: [],
    });
    setError(null);
  };

  const handleVerify = async (parsedIds: string[]) => {
    if (parsedIds.length === 0) return;
    try {
      await verifyMutation.mutateAsync(parsedIds);
    } catch {
      // Error state is already handled by the mutation callbacks.
    }
  };

  const handleSubmit = async (
    name: string,
    parsedIds: string[],
    source: "paste" | "upload",
  ) => {
    setError(null);

    const trimmedName = name.trim();
    if (!trimmedName) {
      setError("Please enter a name for the gene set.");
      return;
    }

    const idsToSubmit =
      verified && resolvedGenes ? resolvedGenes.map((g) => g.geneId) : parsedIds;

    if (idsToSubmit.length === 0) {
      setError("No valid gene IDs to add.");
      return;
    }

    try {
      await createMutation.mutateAsync({
        name: trimmedName,
        geneIds: idsToSubmit,
        source,
      });
    } catch {
      // Error state is already handled by the mutation callbacks.
    }
  };

  return {
    error,
    setError,
    isSubmitting: createMutation.isPending,
    verifying: verifyMutation.isPending,
    resolvedGenes,
    unresolvedIds,
    verified,
    resetVerification,
    handleVerify,
    handleSubmit,
  };
}
