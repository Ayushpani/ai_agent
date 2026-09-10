"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence } from "framer-motion";
import { ChatInput } from "@/components/ChatInput";
import { UserTurn } from "@/components/UserTurn";
import { AssistantTurn, type AssistantTurnData } from "@/components/AssistantTurn";
import { StepState } from "@/components/StepTimeline";
import { streamAsk } from "@/lib/stream";
import { summarizeStage, STAGE_ORDER } from "@/lib/stages";
import type { ResearchDepth, StageName } from "@/lib/types";

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
  const [depth, setDepth] = useState<ResearchDepth>("standard");
  const pinnedToBottom = useRef(true);

  // Follow the stream only while the reader is already at the bottom.
  // Yanking someone back down while they are reading an earlier panel is
  // the other half of what makes chat scrolling feel broken.
  useEffect(() => {
    const onScroll = () => {
      const distanceFromBottom =
        document.documentElement.scrollHeight - window.scrollY - window.innerHeight;
      pinnedToBottom.current = distanceFromBottom < 160;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const scrollToBottom = useCallback((force = false) => {
    if (!force && !pinnedToBottom.current) return;
    requestAnimationFrame(() => {
      window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" });
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
          assistant: {
            id: turnId,
            sessionId,
            steps: [],
            final: null,
            streaming: true,
            startedAt: Date.now(),
            durationMs: null,
          },
        },
      ]);
      setIsStreaming(true);
      // Always jump to a question the user just asked, even if they had
      // scrolled up to read something earlier.
      pinnedToBottom.current = true;
      scrollToBottom(true);

      const updateAssistant = (mutate: (prev: AssistantTurnData) => AssistantTurnData) => {
        setTurns((prev) =>
          prev.map((t) => (t.id === turnId ? { ...t, assistant: mutate(t.assistant) } : t))
        );
      };

      try {
        for await (const event of streamAsk(question, sessionId, IDENTITY, depth)) {
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
            updateAssistant((prev) => ({
              ...prev,
              final: event.result,
              streaming: false,
              durationMs: Date.now() - prev.startedAt,
            }));
            scrollToBottom();
          }
        }
      } catch (err) {
        updateAssistant((prev) => ({
          ...prev,
          streaming: false,
          durationMs: Date.now() - prev.startedAt,
          final: {
            narration: null,
            chart_spec: null,
            query_result: null,
            signals: null,
            panels: [],
            research_plan: null,
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
    [depth, scrollToBottom]
  );

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-20 border-b border-border/70 bg-background/85 backdrop-blur">
        <div className="mx-auto w-full max-w-5xl px-4 py-3">
          <h1 className="text-[16px] font-semibold tracking-tight text-foreground">
            Portfolio Intelligence Agent
          </h1>
          <p className="text-[12.5px] text-muted">
            Every figure traces to a SQL execution or a deterministic calculation — never a
            language-model token.
          </p>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl space-y-6 px-4 pb-40 pt-6">
        {turns.length === 0 && <EmptyState onPick={ask} />}

        <AnimatePresence initial={false}>
          {turns.map((turn) => (
            <div key={turn.id} className="flex flex-col gap-3">
              <UserTurn question={turn.question} />
              <AssistantTurn turn={turn.assistant} />
            </div>
          ))}
        </AnimatePresence>
      </main>

      <div className="fixed inset-x-0 bottom-0 z-20 bg-gradient-to-t from-background via-background to-transparent pb-5 pt-8">
        <div className="mx-auto w-full max-w-5xl px-4">
          <ChatInput onSubmit={ask} disabled={isStreaming} depth={depth} onDepthChange={setDepth} />
        </div>
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
      <p className="pt-2 text-[13px] leading-relaxed text-muted">
        Turn on Deep research below to have the agent plan and run additional breakdowns —
        attribution by segment, period comparisons, concentration — before it answers.
      </p>
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
