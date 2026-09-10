"use client";

import { useRef, type KeyboardEvent } from "react";
import { motion } from "framer-motion";
import { ArrowUp, Loader2, Telescope } from "lucide-react";
import type { ResearchDepth } from "@/lib/types";

export function ChatInput({
  onSubmit,
  disabled,
  depth,
  onDepthChange,
}: {
  onSubmit: (question: string) => void;
  disabled: boolean;
  depth: ResearchDepth;
  onDepthChange: (depth: ResearchDepth) => void;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const value = ref.current?.value.trim();
    if (!value || disabled) return;
    onSubmit(value);
    if (ref.current) {
      ref.current.value = "";
      ref.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const handleInput = () => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  const deep = depth === "deep";

  return (
    <div className="rounded-2xl border border-border bg-surface p-2 shadow-sm transition-colors focus-within:border-accent/50 focus-within:ring-2 focus-within:ring-accent/10">
      <textarea
        ref={ref}
        rows={1}
        placeholder="Ask a question about the loan portfolio..."
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        disabled={disabled}
        className="max-h-40 w-full resize-none bg-transparent px-2 py-2 text-[15px] leading-relaxed text-foreground placeholder:text-muted focus:outline-none disabled:opacity-60"
      />

      <div className="flex items-center justify-between gap-2 px-1 pb-0.5">
        <button
          type="button"
          onClick={() => onDepthChange(deep ? "standard" : "deep")}
          disabled={disabled}
          aria-pressed={deep}
          title="Run additional planned breakdowns before answering. Costs two extra model calls."
          className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12.5px] font-medium transition-colors disabled:opacity-50 ${
            deep
              ? "border-accent/40 bg-accent-soft text-accent-strong"
              : "border-border text-muted hover:text-accent"
          }`}
        >
          <Telescope className="h-3.5 w-3.5" strokeWidth={2} />
          Deep research
          <motion.span
            layout
            className={`ml-0.5 h-1.5 w-1.5 rounded-full ${deep ? "bg-accent" : "bg-transparent"}`}
          />
        </button>

        <button
          onClick={submit}
          disabled={disabled}
          aria-label="Send"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-white transition-colors hover:bg-accent-strong disabled:opacity-40"
        >
          {disabled ? (
            <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2.5} />
          ) : (
            <ArrowUp className="h-4 w-4" strokeWidth={2.5} />
          )}
        </button>
      </div>
    </div>
  );
}
