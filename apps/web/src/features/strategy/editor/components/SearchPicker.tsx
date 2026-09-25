"use client";

import type { RecordType, Search } from "@pathfinder/shared";
import { Combobox, type ComboboxOption } from "@/components/ui/combobox";
import { searchGroupName } from "@/features/strategy/services/searchGroups";

interface SearchPickerProps {
  searches: Search[];
  /** The site's record types. Each group of searches is headed by one. */
  recordTypes: RecordType[];
  value: string | null;
  /** Called with the picked search name (null when cleared). */
  onChange: (nextSearchName: string | null) => void;
  placeholder?: string;
  disabled?: boolean;
}

export function SearchPicker({
  searches,
  recordTypes,
  value,
  onChange,
  placeholder = "Pick a search...",
  disabled,
}: SearchPickerProps) {
  const options: ComboboxOption[] = searches.map((s) => ({
    value: s.name,
    label: s.displayName || s.name,
  }));

  const groupName = searchGroupName(searches, recordTypes);

  return (
    <Combobox
      options={options}
      value={value}
      onChange={(next) => onChange(next)}
      placeholder={placeholder}
      groupBy={(option) => groupName(option.value)}
      emptyMessage="No matching searches."
      {...(disabled !== undefined && { disabled })}
    />
  );
}
