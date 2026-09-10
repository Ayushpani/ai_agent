"use client";

import { useRef, type KeyboardEvent } from "react";
import { ArrowUp, Loader2 } from "lucide-react";

export function ChatInput({
  onSubmit,
  disabled,
}: {
  onSubmit: (question: string) => void;
  disabled: boolean;
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

  return (
    <div className="flex items-end gap-2 rounded-2xl border border-border bg-surface p-2 shadow-sm focus-within:border-accent/50 focus-within:ring-2 focus-within:ring-accent/10">
      <textarea
        ref={ref}
        rows={1}
        placeholder="Ask a question about the loan portfolio..."
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        disabled={disabled}
        className="max-h-40 flex-1 resize-none bg-transparent px-2 py-2 text-[15px] leading-relaxed text-foreground placeholder:text-muted focus:outline-none disabled:opacity-60"
      />
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
  );
}
