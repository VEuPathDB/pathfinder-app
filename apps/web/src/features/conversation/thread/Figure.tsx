import type { ReactElement, ReactNode } from "react";

const CAPTION = "mt-2 text-xs text-muted-foreground";
const NUMBERED_CAPTION = `${CAPTION} text-center italic`;

interface FigureProps {
  title: string | null;
  caption: string | null;
  /** Presents the caption the way a paper does: centered, italic, and
   * prefixed with `figureNumber`. */
  numbered?: boolean;
  /** The caption's number. Null while the thread cannot supply one, which
   * leaves the caption in its plain left form. */
  figureNumber?: number | null;
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
  numbered,
  figureNumber,
  action,
  footer,
  children,
  testId,
}: FigureProps): ReactElement {
  const number = numbered === true ? (figureNumber ?? null) : null;
  const body = (
    <>
      {title !== null ? (
        action != null ? (
          <figcaption className="mb-2 flex items-center justify-between gap-2 text-sm font-medium">
            <span className="min-w-0">{title}</span>
            {action}
          </figcaption>
        ) : (
          <figcaption className="mb-2 text-sm font-medium">{title}</figcaption>
        )
      ) : null}
      {children}
      {caption !== null ? (
        <div
          data-testid="figure-caption"
          className={number === null ? CAPTION : NUMBERED_CAPTION}
        >
          {number === null ? caption : `Figure ${String(number)}. ${caption}`}
        </div>
      ) : null}
      {footer}
    </>
  );
  return (
    <figure data-testid="figure">
      {testId === undefined ? body : <div data-testid={testId}>{body}</div>}
    </figure>
  );
}
