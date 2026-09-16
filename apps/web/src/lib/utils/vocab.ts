export type VocabOption = {
  label: string;
  value: string;
  rawLabel?: string;
  depth?: number;
  displayLabel?: string;
};

export type VocabNode = {
  value: string;
  label: string;
  children?: VocabNode[];
};

function getRecordField(rec: Record<string, unknown>, key: string): unknown {
  return rec[key];
}

function extractValueFromData(data: Record<string, unknown>): unknown {
  return (
    getRecordField(data, "value") ??
    getRecordField(data, "id") ??
    getRecordField(data, "term") ??
    getRecordField(data, "name") ??
    getRecordField(data, "display") ??
    getRecordField(data, "displayName") ??
    getRecordField(data, "label")
  );
}

function extractLabelFromData(
  data: Record<string, unknown>,
  fallback: unknown,
): unknown {
  return (
    getRecordField(data, "display") ??
    getRecordField(data, "displayName") ??
    getRecordField(data, "label") ??
    getRecordField(data, "name") ??
    getRecordField(data, "value") ??
    getRecordField(data, "term") ??
    fallback
  );
}

function isNonNullObject(val: unknown): val is Record<string, unknown> {
  return typeof val === "object" && val != null && !Array.isArray(val);
}

export function extractVocabOptions(vocabulary: unknown, limit = 200): VocabOption[] {
  const options: VocabOption[] = [];
  const seen = new Set<string>();
  const pushOption = (value: string, label?: string, depth = 0) => {
    const trimmedValue = value.trim();
    if (trimmedValue === "" || seen.has(trimmedValue)) {
      return;
    }
    const rawLabel =
      trimmedValue === "@@fake@@" ? "All" : (label ?? trimmedValue).trim();
    const displayLabel = depth > 0 ? `${"- ".repeat(depth)}${rawLabel}` : rawLabel;
    options.push({
      value: trimmedValue,
      label: rawLabel,
      rawLabel,
      depth,
      displayLabel,
    });
    seen.add(trimmedValue);
  };
  const walkTree = (node: Record<string, unknown>, depth = 0) => {
    if (options.length >= limit) return;
    const data = getRecordField(node, "data") as Record<string, unknown> | undefined;
    const rawValue = data != null ? extractValueFromData(data) : undefined;
    const rawLabel = data != null ? extractLabelFromData(data, rawValue) : rawValue;
    const label = rawLabel != null ? String(rawLabel) : "";
    const valueCandidate = rawValue != null ? String(rawValue) : "";
    const value = valueCandidate !== "" ? valueCandidate : label;
    if (value !== "") {
      pushOption(value, label !== "" ? label : value, depth);
    }
    const children = getRecordField(node, "children") as
      Array<Record<string, unknown>> | undefined;
    if (children != null) {
      children.forEach((child) => walkTree(child, depth + 1));
    }
  };
  const walkArray = (entries: unknown[]) => {
    for (const entry of entries) {
      if (options.length >= limit) return;
      if (typeof entry === "string" || typeof entry === "number") {
        pushOption(String(entry));
        continue;
      }
      if (Array.isArray(entry)) {
        const value: unknown = entry[0];
        const label: unknown = entry[1];
        if (value !== undefined) {
          pushOption(String(value), label != null ? String(label) : undefined);
        }
        continue;
      }
      if (isNonNullObject(entry)) {
        const value =
          getRecordField(entry, "value") ??
          getRecordField(entry, "id") ??
          getRecordField(entry, "term") ??
          getRecordField(entry, "name") ??
          getRecordField(entry, "displayName");
        const label =
          getRecordField(entry, "display") ??
          getRecordField(entry, "displayName") ??
          getRecordField(entry, "label") ??
          getRecordField(entry, "name") ??
          value;
        if (value !== undefined) {
          pushOption(String(value), label != null ? String(label) : undefined);
        }
      }
    }
  };
  if (Array.isArray(vocabulary)) {
    walkArray(vocabulary);
    return options;
  }
  if (isNonNullObject(vocabulary)) {
    const record = vocabulary;
    const values =
      getRecordField(record, "values") ??
      getRecordField(record, "items") ??
      getRecordField(record, "terms") ??
      getRecordField(record, "options") ??
      getRecordField(record, "allowedValues");
    if (Array.isArray(values)) {
      walkArray(values);
    } else if (isNonNullObject(values)) {
      Object.entries(values).forEach(([key, val]) => {
        if (typeof val === "string" || typeof val === "number") {
          pushOption(key, String(val));
        } else {
          pushOption(key, undefined);
        }
      });
    } else {
      walkTree(record);
    }
  }
  return options;
}

export function extractVocabTree(vocabulary: unknown): VocabNode[] | null {
  const extractNode = (entry: Record<string, unknown>): VocabNode | null => {
    const dataField = getRecordField(entry, "data");
    const data = (isNonNullObject(dataField) ? dataField : null) ?? entry;
    const rawValue = extractValueFromData(data);
    if (rawValue == null) return null;
    const rawLabel = extractLabelFromData(data, rawValue);
    const entryChildren = getRecordField(entry, "children");
    const children = Array.isArray(entryChildren)
      ? entryChildren
          .map((child: unknown) => (isNonNullObject(child) ? extractNode(child) : null))
          .filter((child): child is VocabNode => child != null)
      : [];
    const value = String(rawValue);
    const label = value === "@@fake@@" ? "All" : String(rawLabel ?? value);
    if (children.length > 0) {
      return { value, label, children };
    }
    return { value, label };
  };

  if (vocabulary == null || typeof vocabulary !== "object") return null;
  if (Array.isArray(vocabulary)) {
    const nodes = vocabulary
      .map((entry: unknown) => (isNonNullObject(entry) ? extractNode(entry) : null))
      .filter((node): node is VocabNode => node != null);
    const hasChildren = nodes.some((node) => (node.children?.length ?? 0) > 0);
    return hasChildren ? nodes : null;
  }

  const record = vocabulary as Record<string, unknown>;
  const values =
    getRecordField(record, "values") ??
    getRecordField(record, "items") ??
    getRecordField(record, "terms") ??
    getRecordField(record, "options");
  if (Array.isArray(values)) {
    const nodes = values
      .map((entry: unknown) => (isNonNullObject(entry) ? extractNode(entry) : null))
      .filter((node): node is VocabNode => node != null);
    const hasChildren = nodes.some((node) => (node.children?.length ?? 0) > 0);
    return hasChildren ? nodes : null;
  }

  const recordChildren = getRecordField(record, "children");
  if (recordChildren != null && Array.isArray(recordChildren)) {
    const root = extractNode(record);
    return root != null ? [root] : null;
  }

  return null;
}
