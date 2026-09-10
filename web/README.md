# Portfolio Intelligence Agent — Web UI

A Next.js chat interface for the agent, talking to the FastAPI backend
(`app/api/main.py`) over Server-Sent Events. Built as an alternative to
the Chainlit UI (`app/ui/chainlit_app.py`) for a fully custom,
animated interface — both front ends drive the same backend and the
same LangGraph pipeline, so nothing here reimplements any agent logic.

Design constraints, deliberately: light theme only (no dark mode), no
emoji anywhere in the UI.

## What it does

- Streams each pipeline stage (classify → generate SQL → execute →
  tools → analyst → narrate → chart) as it actually starts and
  finishes, driven by the backend's real LangGraph event stream — not
  a fake typing animation.
- Shows the generated SQL, row counts, key signals, and analyst
  findings inline as each step completes.
- Reveals the final narration with a word-by-word write-on effect.
- Renders the chart client-side (Recharts) from the same chart-type
  decision and query result the Excel workbook uses, so the two never
  disagree.
- Offers a "Download analysis workbook" link straight to the backend's
  `/download/{session_id}` endpoint.

## Setup

Requires the backend running first (see the repo root README).

```bash
cd web
npm install
cp .env.local.example .env.local   # points at http://localhost:8000 by default
npm run dev
```

Open http://localhost:3000. The backend must have CORS enabled for
this origin — already configured in `app/api/main.py` for
`http://localhost:3000`; add any other origin there before deploying
elsewhere.

## Layout

```
app/            Next.js App Router — layout, global styles, the single chat page
components/     ChatInput, StepTimeline, ChartRenderer, StreamingText, turn components
lib/
  types.ts      TypeScript mirror of the backend's SSE payload shapes
  stream.ts     Parses POST /ask/stream's `data: ...` frames off a fetch() ReadableStream
  stages.ts     Stage labels/icons + per-stage detail summarizer (mirrors
                app/ui/chainlit_app.py's _summarize_stage, so both UIs show the same substance)
```

## Notes

- Each question gets its own `session_id` (not one per browser tab),
  because the backend's download cache is keyed by session — reusing
  one session_id across a whole conversation would make an earlier
  turn's download link silently return the *latest* turn's workbook.
- `EventSource` can't send a POST body, so streaming is done with
  `fetch()` + a manual SSE frame parser (`lib/stream.ts`) instead.
- The identity sent with every request (`EMP0001` / `admin`) is a POC
  stand-in, matching the Chainlit UI's default — wire real auth in
  `app/api/main.py:get_current_employee` before this reaches
  production users, not here.
