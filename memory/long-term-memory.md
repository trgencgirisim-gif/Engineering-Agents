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
