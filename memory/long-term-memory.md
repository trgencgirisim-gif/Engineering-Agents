# Long-Term Memory (Distilled Facts, Preferences, Patterns)

> This file stores persistent knowledge promoted from recent-memory.md.
> Updated nightly by the consolidate-memory skill.
> Only high-value, durable information belongs here.

## User Preferences

<!-- Coding style, tool preferences, communication style, etc. -->

## Project Facts

- **Project:** Engineering Multi-Agent Analysis System
- **Stack:** Python, FastAPI, Streamlit, Anthropic Claude API, ChromaDB
- **Naming convention:** Turkish variable/function names (ajan, mesaj, gecmis, maliyet, yanit, cevap, puan)
- **Agent count:** 76 total (56 domain + 20 support) across 28 engineering domains
- **Analysis modes:** 4 (single, dual, semi-auto, full-auto)
- **Quality threshold:** Score >= 85/100 for early termination in Mode 4

## Recurring Patterns

<!-- Patterns observed across multiple sessions -->

## Key Decisions Log

<!-- Important architectural or design decisions with rationale -->

### [2026-04-04] Token Efficiency — 3 Improvements Plan

**Goal:** Reduce token usage 15-40% on repeat/similar analyses by learning from past work.

**Improvement 1: Unified Domain-Specific RAG Injection**
- Problem: main.py/orchestrator.py don't inject RAG into domain agents or final report (app.py does)
- Solution: New `shared/rag_context.py` with 3 shared functions:
  - `build_domain_message(brief, domain_key, domain_name, rag_store, max_tokens=250)` — injects past domain context + parameters into Round 1 domain agents
  - `build_final_report_context(brief, rag_store, max_tokens=400)` — RAG context + template for final report
  - `build_prompt_engineer_message(brief, rag_store, max_tokens=500)` — enriched brief for prompt engineer
- Integration: All 3 entry points (main.py, app.py, orchestrator.py) use shared functions
- Token budget: 200-250 per domain agent (Round 1 only), 400 final report, 500 prompt engineer

**Improvement 2: Structured Parameter Persistence & Reuse**
- Problem: Parser extracts name/value/unit/confidence but only text summary saved to RAG
- Solution:
  - `Blackboard.export_parameters()` — exports latest params as JSON-safe list
  - `rag/store.py` — persist `parameters_json` in ChromaDB metadata on save
  - `rag/store.py` — new `get_parameters_for_domain()` retrieval method
  - Inject parameter tables into domain agent messages via `build_domain_message()`
- Token impact: ~80 tokens input, saves 200-500 output tokens per agent when values reusable

**Improvement 3: Template-Based Response Guidance**
- Problem: Agents start from scratch structurally, may miss sections → wasted iteration round
- Solution:
  - `rag/store.py` — new `get_analysis_template(query, min_score=85, max_distance=0.30)` 
  - Extracts section headings + word counts from high-quality similar analyses
  - Injects into final report agent and optionally observer
- Token impact: ~100-150 tokens input, can save entire analysis round (20K-50K tokens)

**Implementation Order (7 commits):**
1. `blackboard.py` — `export_parameters()` method
2. `rag/store.py` — parameter persistence + template extraction + param retrieval
3. `shared/rag_context.py` — NEW shared RAG context module
4. `main.py` — integrate shared RAG into all 3 modes + final report
5. `app.py` — replace inline RAG with shared module
6. `orchestrator.py` — add RAG injection
7. Memory update + push

**Critical Files:**
- `shared/rag_context.py` (NEW)
- `rag/store.py` (MODIFY)
- `blackboard.py` (MODIFY — add export_parameters)
- `main.py` (MODIFY — inject RAG in run_tekli/run_cift/run_full_loop + final_rapor)
- `app.py` (MODIFY — replace inline RAG with shared module)
- `orchestrator.py` (MODIFY — add RAG injection)

### [2026-04-10] B2 — Shared Analysis Modes Module

**Problem:** Three entry points (main.py, app.py, orchestrator.py) each implemented the same 3 analysis modes (tekli/cift/full_loop) independently, totaling ~1,700 lines of near-identical logic. The pipeline logic was identical; only the I/O layer differed (SSE emit vs Streamlit vs print).

**Solution:** Callback-based `AnalysisIO` dataclass + pure-logic shared functions in `shared/analysis_modes.py`:
- `AnalysisIO` carries callbacks: `run_agent`, `run_parallel`, `on_event`, `rag_store`, `checkpoint`, `get/set_domain_model`, `on_model_promote`
- `FullLoopHooks` carries optional hooks: `quality_gate`, `quality_gate_retry`, `on_round_start`, `on_round_score`
- Three shared functions: `run_single_analysis()`, `run_dual_analysis()`, `run_full_loop_analysis()`
- `shared/analysis_helpers.py` holds previously-triplicated helpers: `build_context_history()`, `update_blackboard()`, `extract_quality_score()`

**Key architectural insight — model promotion closure:**
- main.py promotes adaptive model via `self.domain_model` attribute (all subsequent calls use it)
- orchestrator.py promotes by mutating `AGENTS[ak]["model"]` dict entries per-agent
- Solution: `on_model_promote(keys) -> restore_fn` callback — each entry point implements differently and returns a closure that reverts its own state

**Quality gate (C5) integration:**
- App.py-only feature; runs after GRUP A results in Round 1 only
- Integrated via `FullLoopHooks.quality_gate` + `quality_gate_retry` — shared core calls them if provided, noop otherwise

**Prep phase placement:**
- Prompt engineering + domain selection stay in entry points (they differ significantly)
- Shared functions only handle the analysis pipeline itself

**Net impact:** ~700 lines eliminated. Each entry point's mode functions now 3-15 lines of adapter code.

**Commits:** 1141a61, 40ab564, 5f806d6, 82df186, + Commit 6 (cleanup + memory + push)

### [2026-03-26] DEBT-6 Session Persistence
- SQLite-based (stdlib, zero deps), WAL mode, thread-safe per-thread connections
- 5 checkpoint points, startup restore, 3 API endpoints, Streamlit sidebar
- English naming: SessionStore, save/load/delete (user preference)

### [2026-03-18] Memory system created
- Three-tier memory: recent (48hr rolling), long-term (distilled), project (active state)
- Nightly consolidation skill promotes recent -> long-term

## Known Issues & Workarounds

<!-- Persistent issues and their solutions -->

## Tool & API Notes

<!-- API quirks, model behavior notes, etc. -->
- Anthropic prompt caching: 2-block strategy (preamble + agent-specific)
- Minimum cache thresholds: Sonnet 1024 tokens, Opus 4096 tokens
- Thinking mode: auto-fallback to non-thinking if API rejects
