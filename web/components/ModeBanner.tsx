"use client";

import { useEffect, useState } from "react";
import { FlaskConical } from "lucide-react";
import { API_BASE_URL } from "@/lib/stream";

/**
 * Says on screen when the backend is scripts/mock_backend.py.
 *
 * The mock returns the same canned answer for every question, and from
 * inside the browser it is indistinguishable from the real agent until
 * you notice nothing changes between queries. That is a confusing way to
 * find out, so the backend reports it on /health and this states it.
 */
export function ModeBanner() {
  const [mocked, setMocked] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE_URL}/health`)
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled) setMocked(Boolean(data?.mocked));
      })
      .catch(() => {
        // The composer surfaces an unreachable backend on the first
        // question; a health-check failure needs no separate alarm.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!mocked) return null;

  return (
    <div className="flex items-center gap-1.5 rounded-full border border-warning/40 bg-warning/10 px-2.5 py-1 text-[11.5px] font-medium text-warning">
      <FlaskConical className="h-3 w-3 shrink-0" strokeWidth={2} />
      Demo mode — every question returns the same canned answer
    </div>
  );
}
