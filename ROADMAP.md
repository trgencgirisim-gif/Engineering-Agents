# Engineering-Agents — Improvement Roadmap

> Strategic improvement plan derived from the 2026-04-11 three-agent system audit.
> Tracks gaps, prioritized features, and implementation status.
>
> **Update rule:** Mark items `DONE` with commit hash when shipped. Mark `IN PROGRESS`
> when actively being worked on. Add notes for any deviation from the plan.

---

## Diagnosis Summary

The platform is feature-rich at the analysis layer (76 agents, blackboard, RAG,
tier1 tools, B2 refactor) but has three categories of gaps surfaced by the audit:

| Category | Severity | Example Evidence |
|---|---|---|
| **Production hardening** | Critical | No tests, no CI, swallowed exceptions (`main.py:73,89,143,197,562`), no health endpoints, hardcoded secrets in `.streamlit/secrets.toml:12-13` |
| **Engineering integrity** | High | Parameters are strings (no Pint), conflict detection uses substring matching (`blackboard.py:598-642`), no golden-set regression tests |
| **Analysis depth** | High | No Monte Carlo, no uncertainty quantification, DOCX-only output, memory files not runtime-integrated |

---

## Phase 1 — Production Hardening (Foundation)

**Why first:** Without tests and CI, every subsequent change is risky. Highest leverage even though it's unglamorous.

| ID | Feature | Files | Effort | Status |
|---|---|---|---|---|
| 1.1 | pytest harness + mocked Anthropic client + fixtures | `tests/`, `conftest.py` | M | IN PROGRESS |
| 1.2 | Golden-set regression tests — 5 reference problems with known-good scores | `tests/golden/` | M | PENDING |
| 1.3 | GitHub Actions CI: ruff + pyright + pytest on every push | `.github/workflows/ci.yml` | S | IN PROGRESS |
| 1.4 | Structured logging — replace `print()` with `logging` + JSON formatter + correlation IDs | `shared/logging_config.py` (NEW) | M | PENDING |
| 1.5 | Fix swallowed exceptions — audit `except Exception: pass` blocks | `main.py`, `orchestrator.py`, `app.py` | S | PENDING |
| 1.6 | Dockerfile + docker-compose (API + Streamlit + ChromaDB volume) | `Dockerfile`, `docker-compose.yml` | S | PENDING |
| 1.7 | Health endpoints: `/health` (liveness), `/ready` (ChromaDB + API key check) | `main.py` | S | PENDING |
| 1.8 | Secrets hygiene: move `.streamlit/secrets.toml` creds to env vars, pydantic-settings | `config/settings.py` (NEW) | S | PENDING |
| 1.9 | Basic API auth: Bearer token middleware + rate limit per key | `main.py` | S | PENDING |
| 1.10 | README rewrite: quickstart, architecture diagram, API docs | `README.md` | S | PENDING |

**Deliverable:** Branch passes `ci.yml`, `docker compose up` runs the full stack,
every session has a correlation ID in logs, regression tests detect prompt drift.

---

## Phase 2 — Engineering Integrity (Core Differentiator)

**Why second:** This is where the platform claims authority. Parameter drift, unit mismatches, and false-negative conflict detection destroy user trust in engineering software.

| ID | Feature | Files | Effort | Status |
|---|---|---|---|---|
| 2.1 | **Pint unit system** in Blackboard — `Entry.value` becomes `pint.Quantity` | `blackboard.py`, `parser.py`, `shared/units.py` (NEW) | L | PENDING |
| 2.2 | **Semantic conflict detection** — replace keyword overlap with sentence-transformer cosine in `find_conflicting_assumptions()` | `blackboard.py:598-642` | M | PENDING |
| 2.3 | **Confidence-weighted conflict resolution** — weight Agent A vs B by `entry.confidence` | `blackboard.py:256-264` | S | PENDING |
| 2.4 | **Parameter schema validation** — JSON-Schema contracts per domain | `config/parameter_schemas.py` (NEW), `parser.py` | M | PENDING |
| 2.5 | **Per-agent cost + quality history** — persist `MALIYET_DETAY` to SQLite | `shared/session_store.py`, `shared/metrics.py` (NEW) | M | PENDING |
| 2.6 | **Agent performance dashboard** — `/api/metrics` + Streamlit tab | `main.py`, `app.py` | M | PENDING |
| 2.7 | **A/B prompt testing framework** — run two prompt versions on golden set | `scripts/ab_test_prompts.py` (NEW) | M | PENDING |
| 2.8 | **Full provenance tracking** — add `prompt_version`, `model_used`, `retry_count` to Blackboard entries | `blackboard.py:29-40` | S | PENDING |

**Deliverable:** Dimensionally-aware parameters, agent quality/cost trends
visible in a dashboard, prompt changes gated by A/B test.

---

## Phase 3 — Analysis Depth (Value Delivery)

| ID | Feature | Files | Effort | Status |
|---|---|---|---|---|
| 3.1 | **Monte Carlo / sensitivity module** — agents emit parameter distributions, blackboard runs N samples | `shared/uncertainty.py` (NEW), `tools/sensitivity_tool.py` (NEW) | L | PENDING |
| 3.2 | **Structured JSON sibling export** alongside DOCX | `report/json_builder.py` (NEW), `main.py` | M | PENDING |
| 3.3 | **Requirements traceability matrix** — agents tag findings with REQ_XX IDs | `parser.py`, `report/sections.py` | M | PENDING |
| 3.4 | **Compliance checker** — ISO/ASME/IEC YAML database + structured pass/fail | `config/compliance_standards.yaml` (NEW), `shared/compliance.py` (NEW) | L | PENDING |
| 3.5 | **Design-of-Experiments support** — Taguchi/full-factorial planner | `shared/doe.py` (NEW) | M | PENDING |
| 3.6 | **PDF export** — true PDF via ReportLab or pandoc | `report/builder.py` | S | PENDING |

---

## Phase 4 — Knowledge & Retrieval Quality

| ID | Feature | Files | Effort | Status |
|---|---|---|---|---|
| 4.1 | **Hybrid BM25 + vector retrieval** — reciprocal rank fusion | `rag/store.py` | M | PENDING |
| 4.2 | **Cross-encoder re-ranker** — quality-weighted | `rag/store.py` | M | PENDING |
| 4.3 | **Sub-section chunking** — chunk by assumptions/risks/findings | `rag/store.py` | M | PENDING |
| 4.4 | **Memory runtime integration** — read `memory/long-term-memory.md` into system prompts | `shared/agent_runner.py`, `memory/loader.py` (NEW) | S | PENDING |
| 4.5 | **Report diff between rounds** — Streamlit tab with parameter/conflict/score deltas | `blackboard.py`, `app.py` | M | PENDING |
| 4.6 | **RAG versioning + invalidation** — mark reports stale when standards change | `rag/store.py` | S | PENDING |

---

## Phase 5 — User Experience

| ID | Feature | Files | Effort | Status |
|---|---|---|---|---|
| 5.1 | **Mid-run cancellation + restart** — `CancelToken` + `/api/sessions/{sid}/cancel` | `main.py`, `shared/analysis_modes.py`, `app.py` | M | PENDING |
| 5.2 | **Cost/time burn-rate estimator** — historical per-agent averages → live ETA | `main.py`, `config/pricing.py` | S | PENDING |
| 5.3 | **Real-time token streaming** in Streamlit | `shared/agent_runner.py`, `app.py` | M | PENDING |
| 5.4 | **Multi-language output** — language detection on brief | `shared/agent_runner.py` | S | PENDING |
| 5.5 | **WebSocket API** — bidirectional control | `main.py` | M | PENDING |
| 5.6 | **Custom report templates** — user-supplied Jinja2 | `report/templates/` | M | PENDING |

---

## Phase 6 — Enterprise / Integration

| ID | Feature | Effort | Status |
|---|---|---|---|
| 6.1 | CAD file ingestion (STEP/IGES via `cadquery` or `pythonocc`) | L | PENDING |
| 6.2 | Data file ingestion (CSV / Excel / HDF5) with auto-RAG indexing | M | PENDING |
| 6.3 | Multi-tenant workspaces with per-user session isolation | L | PENDING |
| 6.4 | Role-based access (engineer / reviewer / viewer) | M | PENDING |
| 6.5 | Audit log + immutable analysis trail for certification workflows | M | PENDING |

---

## Implementation Log

### [2026-04-11] Phase 1 kickoff — Testing Infrastructure
- **Starting with:** 1.1 (pytest harness) + 1.3 (GitHub Actions CI)
- **Strategy:** Build foundation before features. Tests target non-API layer first
  (blackboard, parser, shared/analysis_helpers) — no live Anthropic calls needed.
- **Goal:** Every push runs `ruff + pytest` on CI; golden-set infrastructure ready
  for Phase 1.2.

---

## Currently In Progress

| Phase | Item | Started | Notes |
|-------|------|---------|-------|
| 1 | 1.1 pytest harness | 2026-04-11 | Unit tests for blackboard, parser, analysis_helpers |
| 1 | 1.3 GitHub Actions CI | 2026-04-11 | ruff + pytest matrix |

---

## Next Up (immediate queue after current sprint)

1. **1.2** Golden-set regression tests (5 reference problems)
2. **1.4** Structured logging with correlation IDs
3. **1.5** Fix swallowed exceptions
4. **1.7** Health endpoints
5. **2.1** Pint units in Blackboard (first major engineering-integrity feature)
