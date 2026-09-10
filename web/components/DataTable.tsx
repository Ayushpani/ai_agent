"use client";

import { useState } from "react";
import { formatValue, humanizeField } from "@/lib/format";

const PREVIEW_ROWS = 8;

/**
 * The table view behind every chart. Two jobs: it lets someone audit the
 * numbers a chart is drawn from, and it is the "relief" the palette's
 * contrast warning requires — three categorical slots sit below 3:1 on a
 * light surface, which is only acceptable when the values are also
 * readable as text somewhere.
 */
export function DataTable({ rows }: { rows: Record<string, unknown>[] }) {
  const [expanded, setExpanded] = useState(false);
  if (rows.length === 0) return null;

  const columns = Object.keys(rows[0]);
  const visible = expanded ? rows : rows.slice(0, PREVIEW_ROWS);

  return (
    <div>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="bg-accent-soft/60">
              {columns.map((col) => (
                <th
                  key={col}
                  className="whitespace-nowrap px-3 py-2 text-left font-medium text-foreground"
                >
                  {humanizeField(col)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, i) => (
              <tr key={i} className="border-t border-border hover:bg-accent-soft/40">
                {columns.map((col) => (
                  <td
                    key={col}
                    className="whitespace-nowrap px-3 py-1.5 tabular-nums text-muted"
                  >
                    {formatValue(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > PREVIEW_ROWS && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-2 text-[12.5px] font-medium text-accent hover:text-accent-strong"
        >
          {expanded ? "Show fewer rows" : `Show all ${rows.length} rows`}
        </button>
      )}
    </div>
  );
}
