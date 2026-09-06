import type { ColumnDef } from "@tanstack/react-table";
import type { Classification } from "@pathfinder/shared";
import { Badge } from "@/components/ui/badge";
import { sanitizeHtml } from "@/features/workbench/analysis/utils/sanitizeHtml";
import type { RecordAttribute } from "@pathfinder/shared/generated/types/RecordAttribute";
import type { ClassifiedRecord } from "@pathfinder/shared/generated/types/ClassifiedRecord";

export const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

const CLASSIFICATION_COLUMN_ID = "classification";

const CLASSIFICATION_STYLES: Record<
  Classification,
  {
    label: string;
    variant: "success" | "destructive" | "warning" | "default";
    className?: string;
  }
> = {
  TP: { label: "True Positive", variant: "success" },
  FP: { label: "False Positive", variant: "destructive" },
  FN: { label: "False Negative", variant: "warning" },
  TN: {
    label: "True Negative",
    variant: "default",
    className: "bg-primary/15 text-primary border-transparent",
  },
};

export function getPrimaryKey(record: ClassifiedRecord): string {
  if (record.id.length === 0) {
    return "unknown";
  }
  return record.id.map((k) => k.value).join("/");
}

function ClassificationBadge({ value }: { value: Classification | null }) {
  if (!value) return null;
  const style = CLASSIFICATION_STYLES[value];
  return (
    <Badge variant={style.variant} className={style.className}>
      {style.label}
    </Badge>
  );
}

const HTML_TAG_RE = /<[^>]+>/;

function stripHtml(html: string): string {
  const doc = new DOMParser().parseFromString(html, "text/html");
  return doc.body.textContent;
}

/** Partial shape of a WDK link-attribute JSON blob. */
type JsonLinkBlob = { url?: string; href?: string; displayText?: string };

function tryParseJsonLink(raw: string): { text: string; url: string } | null {
  if (!raw.startsWith("{")) return null;
  try {
    const obj = JSON.parse(raw) as JsonLinkBlob;
    const url = obj.url ?? obj.href;
    if (typeof url === "string") {
      const text = typeof obj.displayText === "string" ? obj.displayText : "Link";
      return { text, url };
    }
  } catch {
    /* not JSON */
  }
  return null;
}

function AttributeValue({ value }: { value: unknown }) {
  if (value == null) return <span className="text-muted-foreground">{"\u2014"}</span>;

  const str = typeof value === "object" ? JSON.stringify(value) : String(value);

  const link = tryParseJsonLink(str);
  if (link) {
    return (
      <a
        href={link.url}
        target="_blank"
        rel="noopener noreferrer"
        onClick={(e) => e.stopPropagation()}
        className="text-primary underline decoration-primary/30 transition hover:decoration-primary"
      >
        {link.text}
      </a>
    );
  }

  if (HTML_TAG_RE.test(str)) return <>{stripHtml(str)}</>;

  return <>{str}</>;
}

export function buildColumns(
  attributes: RecordAttribute[],
  includeClassification: boolean,
): ColumnDef<ClassifiedRecord>[] {
  const attributeColumns: ColumnDef<ClassifiedRecord>[] = attributes.map((attr) => ({
    id: attr.name,
    header: attr.displayName,
    accessorFn: (row) => row.attributes[attr.name],
    enableSorting: attr.isSortable !== false,
    enableHiding: true,
    cell: (info) => <AttributeValue value={info.getValue()} />,
  }));

  if (!includeClassification) {
    return attributeColumns;
  }

  const classificationColumn: ColumnDef<ClassifiedRecord> = {
    id: CLASSIFICATION_COLUMN_ID,
    header: "Class",
    enableSorting: false,
    enableHiding: false,
    cell: (info) => (
      <ClassificationBadge value={info.row.original.classification ?? null} />
    ),
  };

  return [classificationColumn, ...attributeColumns];
}

export function AttributeValueRich({ value }: { value: unknown }) {
  if (value == null) return <span className="text-muted-foreground">{"\u2014"}</span>;

  const str = typeof value === "object" ? JSON.stringify(value) : String(value);

  const link = tryParseJsonLink(str);
  if (link) {
    return (
      <a
        href={link.url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary underline decoration-primary/30 transition hover:decoration-primary"
      >
        {link.text}
      </a>
    );
  }

  if (HTML_TAG_RE.test(str)) {
    // Content is sanitized by sanitizeHtml which strips scripts, event handlers,
    // and only allows safe inline tags (a, b, i, em, strong, span, br, sub, sup).
    const sanitized = sanitizeHtml(str);
    return (
      <span
        className="[&_a]:text-primary [&_a]:underline"
        dangerouslySetInnerHTML={{ __html: sanitized }}
      />
    );
  }

  return <>{str}</>;
}
