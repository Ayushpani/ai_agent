"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Check, Loader2 } from "lucide-react";
import { STAGE_ICON, STAGE_LABEL } from "@/lib/stages";
import type { StageName } from "@/lib/types";

export interface StepState {
  stage: StageName;
  status: "active" | "done";
  detail: { kind: "text" | "sql"; content: string } | null;
}

/** The step list itself. It carries no border or background of its own —
 * ReasoningPanel owns the container it sits inside. */
export function StepTimeline({ steps }: { steps: StepState[] }) {
  if (steps.length === 0) return null;

  return (
    <ol className="divide-y divide-border">
      <AnimatePresence initial={false}>
        {steps.map((step) => (
          <StepRow key={step.stage} step={step} />
        ))}
      </AnimatePresence>
    </ol>
  );
}

function StepRow({ step }: { step: StepState }) {
  const Icon = STAGE_ICON[step.stage];

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="px-4 py-3"
    >
      <div className="flex items-start gap-3">
        <div
          className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border ${
            step.status === "done"
              ? "border-success/30 bg-success/10 text-success"
              : "border-accent/30 bg-accent-soft text-accent"
          }`}
        >
          {step.status === "done" ? (
            <Check className="h-4 w-4" strokeWidth={2.5} />
          ) : (
            <Icon className="h-3.5 w-3.5" strokeWidth={2} />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[15px] font-medium text-foreground">
              {STAGE_LABEL[step.stage]}
            </span>
            {step.status === "active" && (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" strokeWidth={2.5} />
            )}
          </div>

          <AnimatePresence>
            {step.detail && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden"
              >
                <StepDetail detail={step.detail} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.li>
  );
}

function StepDetail({ detail }: { detail: { kind: "text" | "sql"; content: string } }) {
  if (detail.kind === "sql") {
    return (
      <pre className="mt-2 overflow-x-auto rounded-lg bg-[#0f1720] px-3 py-2.5 text-[13px] leading-relaxed text-[#d7e3f0] font-mono">
        {detail.content}
      </pre>
    );
  }

  return (
    <p className="mt-1.5 text-[14px] leading-relaxed text-muted whitespace-pre-wrap">
      {detail.content}
    </p>
  );
}
