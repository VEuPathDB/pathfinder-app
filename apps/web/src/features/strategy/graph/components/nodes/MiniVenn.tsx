"use client";

import { combineOpEnum } from "@pathfinder/shared";

interface MiniVennProps {
  operator: string;
  width?: number;
  height?: number;
  className?: string;
}

interface RegionFlags {
  leftOnly: boolean;
  rightOnly: boolean;
  lens: boolean;
}

function regionFlagsForOperator(operator: string): RegionFlags {
  if (operator === combineOpEnum.UNION) {
    return { leftOnly: true, rightOnly: true, lens: true };
  }
  if (operator === combineOpEnum.INTERSECT) {
    return { leftOnly: false, rightOnly: false, lens: true };
  }
  if (operator === combineOpEnum.LONLY) {
    return { leftOnly: true, rightOnly: false, lens: true };
  }
  if (operator === combineOpEnum.RONLY) {
    return { leftOnly: false, rightOnly: true, lens: true };
  }
  if (operator === combineOpEnum.MINUS) {
    return { leftOnly: true, rightOnly: false, lens: false };
  }
  if (operator === combineOpEnum.RMINUS) {
    return { leftOnly: false, rightOnly: true, lens: false };
  }
  return { leftOnly: false, rightOnly: false, lens: false };
}

const REGION_TRANSITION = "fill-opacity 240ms cubic-bezier(0.4, 0, 0.2, 1)";

const HIGHLIGHT_FILL = "hsl(var(--success))";
const STROKE_COLOR = "hsl(var(--muted-foreground))";

const LEFT_CENTER = { cx: 28, cy: 28 };
const RIGHT_CENTER = { cx: 56, cy: 28 };
const RADIUS = 20;
// Intersection points: x = 42 (midline), y = 28 ± √(400 − 196) ≈ 28 ± 14.283.
const LENS_PATH = "M42 13.71715 A20 20 0 0 1 42 42.28285 A20 20 0 0 1 42 13.71715 Z";
const LEFT_FULL = `M${LEFT_CENTER.cx},${LEFT_CENTER.cy} m-${RADIUS},0 a${RADIUS},${RADIUS} 0 1,0 ${RADIUS * 2},0 a${RADIUS},${RADIUS} 0 1,0 -${RADIUS * 2},0 Z`;
const RIGHT_FULL = `M${RIGHT_CENTER.cx},${RIGHT_CENTER.cy} m-${RADIUS},0 a${RADIUS},${RADIUS} 0 1,0 ${RADIUS * 2},0 a${RADIUS},${RADIUS} 0 1,0 -${RADIUS * 2},0 Z`;

export function MiniVenn({
  operator,
  width = 168,
  height = 56,
  className,
}: MiniVennProps) {
  if (operator === combineOpEnum.COLOCATE) {
    return (
      <svg
        width={width}
        height={height}
        viewBox="0 0 84 56"
        role="img"
        aria-label="colocate operator"
        data-mode="colocate"
        className={className}
      >
        <circle cx={24} cy={28} r={18} fill={HIGHLIGHT_FILL} fillOpacity={0.25} />
        <circle cx={60} cy={28} r={18} fill={HIGHLIGHT_FILL} fillOpacity={0.25} />
        <circle
          cx={24}
          cy={28}
          r={18}
          fill="none"
          stroke={STROKE_COLOR}
          strokeWidth={1.5}
        />
        <circle
          cx={60}
          cy={28}
          r={18}
          fill="none"
          stroke={STROKE_COLOR}
          strokeWidth={1.5}
        />
        <g data-region="colocate-arrow">
          <path
            d="M36 28 H48"
            stroke={HIGHLIGHT_FILL}
            strokeWidth={2}
            strokeLinecap="round"
          />
          <path
            d="M36 28 l3 -3 M36 28 l3 3"
            stroke={HIGHLIGHT_FILL}
            strokeWidth={1.6}
            strokeLinecap="round"
          />
          <path
            d="M48 28 l-3 -3 M48 28 l-3 3"
            stroke={HIGHLIGHT_FILL}
            strokeWidth={1.6}
            strokeLinecap="round"
          />
        </g>
      </svg>
    );
  }

  const regions = regionFlagsForOperator(operator);
  const leftOnlyOpacity = regions.leftOnly ? 0.45 : 0;
  const rightOnlyOpacity = regions.rightOnly ? 0.45 : 0;
  const lensOpacity = regions.lens ? 0.85 : 0;

  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 84 56"
      role="img"
      aria-label={`${operator.toLowerCase()} operator`}
      className={className}
    >
      <defs>
        <mask id="venn-left-only-mask" maskUnits="userSpaceOnUse">
          <path d={LEFT_FULL} fill="white" />
          <path d={RIGHT_FULL} fill="black" />
        </mask>
        <mask id="venn-right-only-mask" maskUnits="userSpaceOnUse">
          <path d={RIGHT_FULL} fill="white" />
          <path d={LEFT_FULL} fill="black" />
        </mask>
      </defs>
      <path
        data-region="left-only"
        data-active={regions.leftOnly ? "true" : "false"}
        d={LEFT_FULL}
        fill={HIGHLIGHT_FILL}
        fillOpacity={leftOnlyOpacity}
        mask="url(#venn-left-only-mask)"
        style={{ transition: REGION_TRANSITION }}
      />
      <path
        data-region="right-only"
        data-active={regions.rightOnly ? "true" : "false"}
        d={RIGHT_FULL}
        fill={HIGHLIGHT_FILL}
        fillOpacity={rightOnlyOpacity}
        mask="url(#venn-right-only-mask)"
        style={{ transition: REGION_TRANSITION }}
      />
      <path
        data-region="lens"
        data-active={regions.lens ? "true" : "false"}
        d={LENS_PATH}
        fill={HIGHLIGHT_FILL}
        fillOpacity={lensOpacity}
        style={{ transition: REGION_TRANSITION }}
      />
      <circle
        cx={LEFT_CENTER.cx}
        cy={LEFT_CENTER.cy}
        r={RADIUS}
        fill="none"
        stroke={STROKE_COLOR}
        strokeWidth={1.5}
      />
      <circle
        cx={RIGHT_CENTER.cx}
        cy={RIGHT_CENTER.cy}
        r={RADIUS}
        fill="none"
        stroke={STROKE_COLOR}
        strokeWidth={1.5}
      />
    </svg>
  );
}
