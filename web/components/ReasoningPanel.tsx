"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, Loader2, Sparkles } from "lucide-react";
import { StepTimeline, type StepState } from "./StepTimeline";
import { STAGE_LABEL } from "@/lib/stages";

/**
 * The whole pipeline trace behind one collapsible header.
 *
 * Open while the answer is being worked out — watching it think is the
 * point — then collapsed once it lands, so a finished transcript reads
 * as question and answer rather than nine cards of machinery. A manual
 * toggle sticks: if someone opens it deliberately, the auto-collapse
 * does not fight them.
 */
export function ReasoningPanel({
  steps,
  streaming,
  durationMs,
}: {
  steps: StepState[];
  streaming: boolean;
  durationMs: number | null;
}) {
  const [open, setOpen] = useState(streaming);
  const userToggled = useRef(false);
  const wasStreaming = useRef(streaming);

  useEffect(() => {
    if (wasStreaming.current && !streaming && !userToggled.current) {
      setOpen(false);
    }
    wasStreaming.current = streaming;
  }, [streaming]);

  if (steps.length === 0) return null;

  const activeStage = steps.find((s) => s.status === "active")?.stage;
  const label = streaming
    ? activeStage
      ? STAGE_LABEL[activeStage]
      : "Working"
    : durationMs
      ? `Reasoned for ${(durationMs / 1000).toFixed(1)}s`
      : "Reasoning";

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface">
      <button
        onClick={() => {
          userToggled.current = true;
          setOpen((v) => !v);
        }}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-left transition-colors hover:bg-accent-soft/50"
      >
        {streaming ? (
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-accent" strokeWidth={2.5} />
        ) : (
          <Sparkles className="h-3.5 w-3.5 shrink-0 text-accent" strokeWidth={2} />
        )}

        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            key={label}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.18 }}
            className="min-w-0 flex-1 truncate text-[13.5px] font-medium text-foreground"
          >
            {label}
          </motion.span>
        </AnimatePresence>

        <span className="shrink-0 text-[12px] text-muted">
          {steps.length} step{steps.length === 1 ? "" : "s"}
        </span>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-muted transition-transform duration-200 ${
            open ? "rotate-180" : ""
          }`}
          strokeWidth={2}
        />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="border-t border-border">
              <StepTimeline steps={steps} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
