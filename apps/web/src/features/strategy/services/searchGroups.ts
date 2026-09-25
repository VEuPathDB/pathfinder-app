import type { RecordType, Search } from "@pathfinder/shared";

/** Names the group a search option falls in: its record type's display name. */
export function searchGroupName(
  searches: Search[],
  recordTypes: RecordType[],
): (searchName: string) => string {
  const recordTypeOf = new Map(searches.map((s) => [s.name, s.recordType]));
  const displayNameOf = new Map(
    recordTypes.map((rt) => [
      rt.name,
      rt.displayName !== "" ? rt.displayName : rt.name,
    ]),
  );
  return (searchName) => {
    const recordType = recordTypeOf.get(searchName) ?? "";
    return displayNameOf.get(recordType) ?? recordType;
  };
}
