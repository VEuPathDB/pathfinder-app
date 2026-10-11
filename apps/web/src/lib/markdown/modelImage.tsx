import type { ComponentProps } from "react";

type ModelImageProps = ComponentProps<"img"> & { node?: unknown };

export function ModelImage({ alt }: ModelImageProps) {
  return <span>{alt}</span>;
}

export const modelMarkdownComponents = { img: ModelImage };
