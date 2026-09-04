import { useQuery } from "@tanstack/react-query";
import { geneSetsListOptions } from "@/features/workbench/api/geneSets";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";

export function useGeneSetsQuery(siteId: string) {
  const { data: authStatus } = useQuery(authStatusOptions(siteId));
  const signedIn = authStatus?.signedIn === true;

  return useQuery({
    ...geneSetsListOptions(siteId),
    enabled: signedIn && siteId !== "",
  });
}
