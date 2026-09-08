import type { ReactElement, ReactNode } from "react";

import { ExhibitCitation } from "./ExhibitCitation";
import { exhibitAnchorId, exhibitLabel, type ExhibitIdentity } from "./exhibits";

const CAPTION = "mt-2 text-xs text-muted-foreground";
const NUMBERED_CAPTION = `${CAPTION} text-center italic`;

interface FigureProps {
  title: string | null;
  caption: string | null;
  /** Which counter numbers this exhibit, and its number. A numbered exhibit
   * presents its caption the way a paper does, carries the anchor a citation
   * jumps to, and offers the control that copies that citation. */
  exhibit?: ExhibitIdentity;
  /** Rendered at the right end of the title row. */
  action?: ReactNode;
  /** The readouts and disclosures, rendered after the caption. */
  footer?: ReactNode;
  children: ReactNode;
  testId?: string;
}

/** A typed result in the reading flow: a title, the body, and a caption that
 * carries the numbers. `testId` names the part the figure draws, and wraps the
 * title and the caption with it. */
export function Figure({
  title,
  caption,
  exhibit,
  action,
  footer,
  children,
  testId,
}: FigureProps): ReactElement {
  const kind = exhibit?.kind ?? "figure";
  const number = exhibit?.number ?? null;
  const citation =
    number === null ? null : <ExhibitCitation kind={kind} number={number} />;
  const head =
    title === null && citation === null ? null : citation === null && action == null ? (
      <figcaption className="mb-2 text-sm font-medium">{title}</figcaption>
    ) : (
      <figcaption className="mb-2 flex items-center justify-between gap-2 text-sm font-medium">
        <span className="min-w-0">{title}</span>
        {citation}
        {action}
      </figcaption>
    );
  const body = (
    <>
      {head}
      {children}
      {caption !== null ? (
        <div
          data-testid="figure-caption"
          className={number === null ? CAPTION : NUMBERED_CAPTION}
        >
          {number === null ? caption : `${exhibitLabel(kind, number)}. ${caption}`}
        </div>
      ) : null}
      {footer}
    </>
  );
  return (
    <figure
      data-testid="figure"
      {...(number === null ? {} : { id: exhibitAnchorId(kind, number) })}
    >
      {testId === undefined ? body : <div data-testid={testId}>{body}</div>}
    </figure>
  );
}
