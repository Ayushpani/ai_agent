"use client";

import { useEffect, useState } from "react";

/**
 * Reveals text word-by-word rather than dumping the whole narration in
 * at once. The backend returns the narration as a single completed
 * string (no token-level streaming from the LLM provider), so this
 * simulates the "being written" feel client-side once it arrives —
 * fast enough not to feel slow, slow enough to read as deliberate.
 */
export function StreamingText({ text, className }: { text: string; className?: string }) {
  // Callers pass `key={text}` so a new narration mounts a fresh instance
  // instead of this effect needing to reset state mid-lifecycle.
  const words = text.split(/(\s+)/);
  const [visibleCount, setVisibleCount] = useState(0);

  useEffect(() => {
    if (words.length === 0) return;

    let i = 0;
    const interval = setInterval(() => {
      i += 1;
      setVisibleCount(i);
      if (i >= words.length) clearInterval(interval);
    }, 14);

    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <p className={className} style={{ whiteSpace: "pre-wrap" }}>
      {words.slice(0, visibleCount).join("")}
      {visibleCount < words.length && (
        <span className="inline-block w-[2px] h-[1em] align-middle bg-accent/70 animate-pulse ml-0.5" />
      )}
    </p>
  );
}
