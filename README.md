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
├── api/            FastAPI routes (the request boundary)
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

Generate a synthetic portfolio and run the deterministic pipeline end to
end (no LLM calls involved):

```python
from ingestion.synthetic_data import generate_synthetic_mis
from ingestion.pipeline import run_ingestion_from_dataframe

for i, month in enumerate(["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]):
    run_ingestion_from_dataframe(generate_synthetic_mis(n_loans=2000, seed=i), month)
```

Then run the test suite, which exercises the full graph (router →
SQL generator → DuckDB → tools → analyst → narrator → chart) with the
LLM stages mocked, so it needs no API keys and no network access:

```bash
pytest tests/ -q
```

## Running for real

```bash
# API
uvicorn app.api.main:app --reload

# Chat UI
chainlit run app/ui/chainlit_app.py
```

`POST /ask` with `{"session_id", "question", "identity": {"employee_id", "role"}}`
returns the narrated answer, chart spec, and signals JSON; `GET
/download/{session_id}` returns the Excel workbook for the last chartable
result in that session.

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
- `forecast_tracking_error` and multi-level `decompose` wiring into the
  graph are implemented as standalone tools (`app/tools/forecast.py`,
  `app/tools/stats.py`) with unit tests, but the graph's fixed-per-intent
  sequencing (§7.6) currently calls the single-level path; wiring the
  finer-grained decomposition and cross-request tracking-error lookup is
  the natural next increment once real multi-month data exists.
- Storage is local Parquet only; the S3 `httpfs` swap (doc §5.3 Phase 2)
  is a connection-string change with no code change to the SQL layer,
  but isn't wired up here since the POC doesn't need it.
