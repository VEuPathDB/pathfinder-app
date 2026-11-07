"use client";

import { replyLinksSchema } from "@pathfinder/shared/generated/zod/replyLinksSchema";
import { createContext, use, type ComponentProps, type ReactElement } from "react";

import type { StructuralPart } from "../parts";

export const VouchedLinks = createContext<ReadonlySet<string>>(new Set());

function isLinksPart(part: StructuralPart): boolean {
  return (
    part.type === "data-reply-links" ||
    (part.type === "data" && part.name === "reply-links")
  );
}

export function vouchedLinksOf(
  content: readonly StructuralPart[],
): ReadonlySet<string> {
  return new Set(
    content
      .filter(isLinksPart)
      .flatMap((part) => replyLinksSchema.safeParse(part.data).data?.links ?? []),
  );
}

type VouchedLinkProps = ComponentProps<"a"> & { node?: unknown };

export function VouchedLink({ href, children }: VouchedLinkProps): ReactElement {
  const vouched = use(VouchedLinks);
  if (href === undefined || !vouched.has(href)) return <span>{children}</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}
