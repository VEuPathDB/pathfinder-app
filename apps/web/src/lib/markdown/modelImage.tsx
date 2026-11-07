import type { ComponentProps } from "react";

type ModelImageProps = ComponentProps<"img"> & { node?: unknown };

export function ModelImage({ alt }: ModelImageProps) {
  return <span>{alt}</span>;
}

type ModelLinkProps = ComponentProps<"a"> & { node?: unknown };

export function ModelLinkText({ children }: ModelLinkProps) {
  return <span>{children}</span>;
}

export const modelMarkdownComponents = { img: ModelImage, a: ModelLinkText };
