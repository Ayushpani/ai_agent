# Portfolio Intelligence Agent

A natural-language analytical agent over an NBFC/HFC loan-portfolio MIS
extract. An employee asks a business question in chat; the system returns
a narrated analytical answer and, where appropriate, a downloadable Excel
workbook with a native-charted dashboard built specifically for that
question.

Full design rationale lives in the architecture document this repo
implements. Three principles drive every decision here:

1. **The LLM never does arithmetic.** It generates SQL and interprets
   pre-computed signals; every number in every output traces to a
   specific SQL execution or deterministic Python calculation.
2. **The pipeline is deterministic in structure.** A router picks one of
   a small number of fixed intent flows; the same guarded tools run in
   the same order every time (see `app/tools/`, `app/graph/build.py`).
3. **The agent disambiguates rather than guesses** wherever the data has
   structural ambiguity (LAN vs. UCIC vs. Finance exposure level; gross
   vs. own-share on co-lent loans) — see the forced-disambiguation rule
   below.

Zero paid API spend: every LLM call targets a free-tier endpoint
(OpenRouter, Cloudflare Workers AI) through LiteLLM, with an ordered
per-stage fallback chain and a quota monitor that pre-empts calls a
provider would reject anyway.

## Layout

```
app/
├── api/            FastAPI routes (the request boundary; /ask, /ask/stream, /download)
├── ui/             Chainlit chat app
├── graph/          LangGraph state machine (nodes, edges, model router)
├── prompts/        Router, SQL, Analyst, Narrator — versioned text files
├── tools/          Deterministic Python: data access, stats, forecast,
│                   data-quality, chart decision, Excel workbook builder
├── models/         Pydantic schemas for every LLM output + tool boundary
├── security/       SQL validator (sqlglot) + access-scope resolver
└── observability/  Structured logging, quota monitor, audit log
ingestion/          Excel -> mask -> melt -> Parquet snapshot pipeline
config/             schema_card.yaml, glossary.yaml, access_policies.yaml
web/                Next.js chat UI (alternative to Chainlit) — see web/README.md
tests/
├── unit/           Tool-level tests, no LLM or network dependency
├── integration/    Golden-question suite against the graph (LLM mocked)
└── adversarial/    SQL-injection + PII-leak suites
```

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in OPENROUTER_API_KEY / CLOUDFLARE_API_TOKEN
```

## Try it without any data or API keys

Seed a synthetic portfolio:

```bash
python scripts/seed_synthetic_data.py --months 8 --loans 2000
```

Run the UI with the model calls stubbed — every other layer (SQL
validation, access scoping, DuckDB, the statistical tools, the workbook
builder) runs for real:

```bash
python scripts/mock_backend.py --slow   # terminal 1
cd web && npm run dev                   # terminal 2
```

**The mock returns the same canned answer to every question.** It stubs
the model calls and ignores what you typed, so it is for working on the
interface, not for evaluating the agent — the UI shows a "Demo mode"
chip while it is connected. For answers that actually vary, run the real
backend (`uvicorn app.api.main:app --reload`) with your keys in `.env`.

Or run the test suite, which exercises the full graph in both depths
with the LLM stages mocked, so it needs no API keys and no network:

```bash
pytest tests/ -q
```

Tests ingest into a temp directory (via `PORTFOLIO_CURATED_ROOT`), so
running them never disturbs the dataset you seeded above.

## Running for real

```bash
# API
uvicorn app.api.main:app --reload
```

Two interface options, both driven by the same API and the same graph:

```bash
# Option A: Chainlit chat UI
chainlit run app/ui/chainlit_app.py -w

# Option B: Next.js chat UI (custom animated interface, see web/README.md)
cd web && npm install && npm run dev
```

`POST /ask` with `{"session_id", "question", "identity": {"employee_id", "role"}}`
returns the narrated answer, chart spec, and signals JSON in one response.
`POST /ask/stream` returns the same information as Server-Sent Events, one
event per pipeline stage as it actually starts/finishes — what the Next.js
UI's live step timeline is built on. `GET /download/{session_id}` returns
the Excel workbook for the last chartable result in that session.

## Deep research

Standard depth answers a question with one query. Deep depth — opt-in per
request, from the toggle in the chat input or `"research_depth": "deep"`
on the API — inserts a planned investigation round:

```
Tools -> plan_research -> run_probes -> synthesize -> Narrator
```

`plan_research` asks a model **which** follow-up investigations are worth
running. `app/tools/probes.py` decides **how** each becomes SQL, from a
closed catalog: `decompose_by`, `trend_by_segment`, `period_comparison`,
`concentration`, `distribution`, `related_metric`.

The planner never writes SQL, for two reasons. Free-tier models are
already unreliable at producing one correct query — four more free-form
statements multiply that failure mode. And the metric/dimension it picks
are the only LLM-chosen values that reach SQL at all, so both are
allow-listed against the caller's role-filtered schema card before
interpolation: an invented column, or one the role may not see, is
rejected rather than substituted (`tests/unit/test_probes.py`).

Each probe is measured with the same deterministic tools as the headline
and carries a **computed** one-line headline, so panel text cannot drift
from panel numbers. `synthesize` then reasons across every panel at once
rather than restating each in turn. A probe that fails becomes a panel
carrying its error — three good panels beat none.

Cost: one planner call plus one synthesis call on top of the standard
pipeline. The probes are pure SQL.

## The forced-disambiguation rule

The portfolio has three exposure-level dimensions (LAN / UCIC / Finance)
and two share bases (gross / own-share) for the same underlying loans.
"Our 90+ AUM in Maharashtra" has up to six different correct answers.
Everywhere else in the system the agent answers directly; here — and
only here — it asks, because a fluent-sounding wrong number in this
dimension is more dangerous than one clarifying turn. See
`app/prompts/router.txt`, `app/prompts/disambiguation.txt`, and
`tests/integration/test_golden_questions.py::test_forced_disambiguation_short_circuits_before_sql`.

## Security & privacy posture

- **PII masking at ingestion** (`ingestion/mask.py`): direct identifiers
  are nulled or deterministically hashed before any Parquet write — no
  raw name/Aadhaar/UCID/customer-ID value exists past stage [3] of the
  pipeline.
- **SQL validation** (`app/security/sql_validator.py`): every LLM-generated
  string is parsed with `sqlglot`; only a single read-only `SELECT` with
  the `{ACCESS_SCOPE_FILTER}` placeholder passes. DDL/DML, multi-statement
  payloads, and `SELECT ... INTO` are all rejected — see
  `tests/adversarial/test_sql_injection.py` for the specific payloads this
  is exercised against.
- **Row/column access control** (`app/security/access_scope.py`,
  `config/access_policies.yaml`): the employee's role determines the row
  filter and denied columns *after* SQL generation, using values the LLM
  never sees — it cannot bypass a scope it doesn't control.
- **Audit trail** (`app/observability/audit_log.py`): every chat turn
  writes an immutable record — question, generated SQL (raw and
  scope-substituted), tool sequence, model IDs, latencies, narration.
- **No production data without sign-off** (doc §9.3): demo and develop
  against `ingestion/synthetic_data.py` until written data-retention
  confirmation from both LLM providers and client DPDP/InfoSec approval
  are in hand.

## What's a POC simplification, deliberately

- `app/graph/nodes.py:tools_node` infers metric/time/category columns
  from a query result's dtype and column-name heuristics. A production
  build should instead have the SQL Generator declare its own output
  column roles so this isn't inferred.
- `forecast_tracking_error` is implemented and unit-tested
  (`app/tools/forecast.py`) but not yet wired into the graph — it needs a
  store of what was previously forecast for a series, which the POC's
  in-memory session cache doesn't provide.
- Deep research goes exactly one level deep: the planner proposes probes
  against the headline, and the probes do not themselves spawn
  follow-ups. That bound is deliberate (it keeps cost and latency
  predictable), but a genuinely iterative loop — synthesise, decide
  what's still unexplained, probe again — is the natural next increment.
- Storage is local Parquet only; the S3 `httpfs` swap (doc §5.3 Phase 2)
  is a connection-string change with no code change to the SQL layer,
  but isn't wired up here since the POC doesn't need it.
