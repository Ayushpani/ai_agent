const NUMBER = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return NUMBER.format(value);
  return String(value);
}

/** Indian numbering for axis ticks — a portfolio figure reads as
 * "1.4Cr" to this audience, not "14M". */
export function formatCompact(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_00_00_000) return `${(value / 1_00_00_000).toFixed(1)}Cr`;
  if (abs >= 1_00_000) return `${(value / 1_00_000).toFixed(1)}L`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

export function formatPercent(value: number, withSign = true): string {
  const sign = withSign && value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

/** Column names reach the UI as they come out of SQL ("first_period").
 * Series legends and axis labels are read by business users, so present
 * them as words — but only for machine-looking names, so a real segment
 * value like "BL-STL" or "Branch-RAJ-4" passes through untouched. */
export function humanizeField(name: string): string {
  if (!/^[a-z0-9_]+$/.test(name)) return name;
  return name
    .split("_")
    .filter(Boolean)
    .map((word, i) => (i === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word))
    .join(" ");
}
