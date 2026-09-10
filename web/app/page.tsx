"use client";

import { useCallback, useRef, useState } from "react";
import { AnimatePresence } from "framer-motion";
import { ChatInput } from "@/components/ChatInput";
import { UserTurn } from "@/components/UserTurn";
import { AssistantTurn, type AssistantTurnData } from "@/components/AssistantTurn";
import { StepState } from "@/components/StepTimeline";
import { streamAsk } from "@/lib/stream";
import { summarizeStage, STAGE_ORDER } from "@/lib/stages";
import type { StageName } from "@/lib/types";

// POC identity stand-in for the OIDC-derived identity in production
// (mirrors app/ui/chainlit_app.py's on_chat_start defaults).
const IDENTITY = { employee_id: "EMP0001", role: "admin" };

interface ConversationTurn {
  id: string;
  question: string;
  assistant: AssistantTurnData;
}

const EXAMPLE_QUESTIONS = [
  "What is the trend in 90+ AUM (Finance level, own-share) in Maharashtra over the last 6 months?",
  "Compare principal outstanding across regions",
  "How many active loans do we have?",
];

export default function Home() {
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    });
  }, []);

  const ask = useCallback(
    async (question: string) => {
      const turnId = crypto.randomUUID();
      const sessionId = crypto.randomUUID();

      setTurns((prev) => [
        ...prev,
        {
          id: turnId,
          question,
          assistant: { id: turnId, sessionId, steps: [], final: null, streaming: true },
        },
      ]);
      setIsStreaming(true);
      scrollToBottom();

      const updateAssistant = (mutate: (prev: AssistantTurnData) => AssistantTurnData) => {
        setTurns((prev) =>
          prev.map((t) => (t.id === turnId ? { ...t, assistant: mutate(t.assistant) } : t))
        );
      };

      try {
        for await (const event of streamAsk(question, sessionId, IDENTITY)) {
          if (event.kind === "stage_start") {
            updateAssistant((prev) => ({
              ...prev,
              steps: upsertStep(prev.steps, { stage: event.stage, status: "active", detail: null }),
            }));
            scrollToBottom();
          } else if (event.kind === "stage_end") {
            const detail = summarizeStage(event);
            updateAssistant((prev) => ({
              ...prev,
              steps: upsertStep(prev.steps, { stage: event.stage, status: "done", detail }),
            }));
            scrollToBottom();
          } else if (event.kind === "final") {
            updateAssistant((prev) => ({ ...prev, final: event.result, streaming: false }));
            scrollToBottom();
          }
        }
      } catch (err) {
        updateAssistant((prev) => ({
          ...prev,
          streaming: false,
          final: {
            narration: null,
            chart_spec: null,
            query_result: null,
            signals: null,
            error:
              err instanceof Error
                ? `Could not reach the agent backend: ${err.message}`
                : "Could not reach the agent backend.",
            final_sql: null,
          },
        }));
      } finally {
        setIsStreaming(false);
        scrollToBottom();
      }
    },
    [scrollToBottom]
  );

  return (
    <div className="mx-auto flex h-dvh w-full max-w-3xl flex-col px-4">
      <header className="flex flex-col gap-1 py-6">
        <h1 className="text-[22px] font-semibold tracking-tight text-foreground">
          Portfolio Intelligence Agent
        </h1>
        <p className="text-[14px] text-muted">
          Natural-language analytics over the loan-portfolio MIS. Every figure traces to a SQL
          execution or a deterministic calculation — never a language-model token.
        </p>
      </header>

      <div ref={scrollRef} className="flex-1 space-y-6 overflow-y-auto pb-4">
        {turns.length === 0 && <EmptyState onPick={ask} />}

        <AnimatePresence initial={false}>
          {turns.map((turn) => (
            <div key={turn.id} className="flex flex-col gap-3">
              <UserTurn question={turn.question} />
              <AssistantTurn turn={turn.assistant} />
            </div>
          ))}
        </AnimatePresence>
      </div>

      <div className="sticky bottom-0 bg-background pb-6 pt-2">
        <ChatInput onSubmit={ask} disabled={isStreaming} />
      </div>
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="flex flex-col gap-3 pt-10">
      <p className="text-[14px] text-muted">Try one of these:</p>
      <div className="flex flex-col gap-2">
        {EXAMPLE_QUESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => onPick(q)}
            className="w-fit rounded-xl border border-border bg-surface px-4 py-2.5 text-left text-[14px] text-foreground transition-colors hover:border-accent/40 hover:bg-accent-soft"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

function upsertStep(steps: StepState[], next: StepState): StepState[] {
  const existingIndex = steps.findIndex((s) => s.stage === next.stage);
  if (existingIndex === -1) {
    return [...steps, next].sort(
      (a, b) => STAGE_ORDER.indexOf(a.stage as StageName) - STAGE_ORDER.indexOf(b.stage as StageName)
    );
  }
  const copy = [...steps];
  copy[existingIndex] = next;
  return copy;
}
