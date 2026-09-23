import type { EdaFilter } from "@pathfinder/shared/generated/types/EdaFilter";

const SUMMARISED_VALUES = 3;

function shortList(values: readonly (string | number)[]): string {
  return values.length > SUMMARISED_VALUES
    ? `${String(values.length)} values`
    : values.join(", ");
}

export function filterSummary(filter: EdaFilter): string {
  switch (filter.type) {
    case "stringSet":
      return shortList(filter.stringSet);
    case "numberSet":
      return shortList(filter.numberSet);
    case "dateSet":
      return `${String(filter.dateSet.length)} dates`;
    case "numberRange":
      return `${String(filter.min)} to ${String(filter.max)}`;
    case "dateRange":
      return `${filter.min.slice(0, 10)} to ${filter.max.slice(0, 10)}`;
    case "longitudeRange":
      return `${String(filter.left)} to ${String(filter.right)}`;
    case "multiFilter":
      return `${filter.operation} of ${String(filter.subFilters.length)}`;
  }
}
