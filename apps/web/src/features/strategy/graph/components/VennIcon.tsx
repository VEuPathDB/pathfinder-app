"use client";

import { combineOpEnum } from "@pathfinder/shared";

export function VennIcon({
  operator,
  width = 24,
}: {
  operator: string;
  width?: number;
}) {
  const stroke = "hsl(var(--muted-foreground))";
  const highlight = "hsl(var(--success))";
  const bg = "hsl(var(--card))";

  // Standard venn: centers (14,12) and (22,12), r=8.
  // Intersection points are (18, 12 ± sqrt(64-16)) = (18, 12 ± 6.9282)
  // Lens boundary is one arc from each circle.
  const overlapPath = "M18 5.0718 A8 8 0 0 1 18 18.9282 A8 8 0 0 1 18 5.0718 Z";

  return (
    <svg
      width={width}
      height={Math.round((width * 2) / 3)}
      viewBox="0 0 36 24"
      aria-hidden="true"
    >
      {/* Highlight selected region(s) */}
      {operator === combineOpEnum.UNION && (
        <>
          <circle cx="14" cy="12" r="8" fill={highlight} fillOpacity="0.35" />
          <circle cx="22" cy="12" r="8" fill={highlight} fillOpacity="0.35" />
        </>
      )}
      {operator === combineOpEnum.INTERSECT && (
        <path d={overlapPath} fill={highlight} fillOpacity="0.9" />
      )}
      {operator === combineOpEnum.LONLY && (
        <circle cx="14" cy="12" r="8" fill={highlight} fillOpacity="0.5" />
      )}
      {operator === combineOpEnum.RONLY && (
        <circle cx="22" cy="12" r="8" fill={highlight} fillOpacity="0.5" />
      )}
      {operator === combineOpEnum.MINUS && (
        <>
          <circle cx="14" cy="12" r="8" fill={highlight} fillOpacity="0.5" />
          <path d={overlapPath} fill={bg} />
        </>
      )}
      {operator === combineOpEnum.RMINUS && (
        <>
          <circle cx="22" cy="12" r="8" fill={highlight} fillOpacity="0.5" />
          <path d={overlapPath} fill={bg} />
        </>
      )}
      {operator === combineOpEnum.COLOCATE && (
        <>
          {/* Not a set operator; show "near" as two separated sets + distance arrow */}
          <circle cx="12" cy="12" r="7" fill={highlight} fillOpacity="0.25" />
          <circle cx="24" cy="12" r="7" fill={highlight} fillOpacity="0.25" />
          <path
            d="M16.5 12H19.5"
            stroke={highlight}
            strokeWidth="2"
            strokeLinecap="round"
          />
          <path
            d="M16.5 12l1.2-1.2M16.5 12l1.2 1.2"
            stroke={highlight}
            strokeWidth="1.6"
            strokeLinecap="round"
          />
          <path
            d="M19.5 12l-1.2-1.2M19.5 12l-1.2 1.2"
            stroke={highlight}
            strokeWidth="1.6"
            strokeLinecap="round"
          />
        </>
      )}
      {/* outlines */}
      {operator === combineOpEnum.COLOCATE ? (
        <>
          <circle cx="12" cy="12" r="7" fill="none" stroke={stroke} strokeWidth="1.5" />
          <circle cx="24" cy="12" r="7" fill="none" stroke={stroke} strokeWidth="1.5" />
        </>
      ) : (
        <>
          <circle cx="14" cy="12" r="8" fill="none" stroke={stroke} strokeWidth="1.5" />
          <circle cx="22" cy="12" r="8" fill="none" stroke={stroke} strokeWidth="1.5" />
        </>
      )}
    </svg>
  );
}
