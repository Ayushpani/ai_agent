/**
 * Chart color roles.
 *
 * The categorical slots below are the dataviz reference palette, in its
 * validated slot order. That order is the colorblind-safety mechanism,
 * not decoration: it clears the adjacent-pair CVD and normal-vision
 * gates (worst adjacent CVD ΔE 9.1, normal-vision ΔE 19.6 on the light
 * surface). Assign slots in order and never cycle them — a ninth series
 * is folded away, not given a generated hue.
 *
 * The product's navy (#1f4e79) stays UI chrome — headings, buttons,
 * borders. It is deliberately NOT a series color: a monochrome navy ramp
 * used categorically hard-fails the chroma-floor and normal-vision gates
 * (adjacent steps read as the same color), which is what the first cut
 * of this file did.
 */

export const SERIES_COLORS = [
  "#2a78d6", // blue
  "#eb6834", // orange
  "#1baf7a", // aqua
  "#eda100", // yellow
  "#e87ba4", // magenta
  "#008300", // green
  "#4a3aa7", // violet
  "#e34948", // red
] as const;

/** Single-series marks use slot 1, so one-series charts stay consistent
 * with the first series of any multi-series chart beside them. */
export const PRIMARY_SERIES = SERIES_COLORS[0];

/** Past this, folding beats a generated hue. */
export const MAX_SERIES = SERIES_COLORS.length;

export const GRID_STROKE = "#e8ecf1";
export const AXIS_TEXT = "#5b6472";

export function seriesColor(index: number): string {
  return SERIES_COLORS[index % SERIES_COLORS.length];
}
