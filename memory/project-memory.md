# Project Memory (Active Project State)

> Tracks the current state of active work items, branches, and in-flight changes.
> Updated by the consolidate-memory skill and during active sessions.

## Active Branches

| Branch | Purpose | Status |
|--------|---------|--------|
| `claude/add-skills-improve-caching-Yu7GY` | Skills system + caching improvements | in-progress |

## Current Work Items

### Tier 1 Tool Wrappers
- **Status:** Complete (25 tools)
- **Location:** `tools/tier1/`
- **Tools:** cantera, coolprop, fenics, opensees, python_control, materials_project, matminer, pyspice, pybullet, pypsa, brightway2, capytaine, rayoptics, meep, openmc, openrocket, reliability, su2, openfoam, opensim, febio, openmodelica, freecad, dwsim, sumo
- **Script:** `scripts/update_skill_prompts.py` — scans tool wrappers, updates SKILL.md files

### Plan 2 Patch — LLM Tool Calling Quality (4-layer)
- **Status:** Complete
- **Layer 1:** All 25 tool `_description()` rewritten with WHEN TO CALL / DO NOT CALL / REQUIRED format
- **Layer 2:** Solver obligation block added to all 54 domain SKILL.md files
- **Layer 3:** Few-shot examples for 5 critical domains (yanma, yapisal, kontrol, malzeme, termodinamik)
- **Layer 4:** TOOL_REMINDER_PREFIX in core.py prepends tool-check to user messages

### System Integrity Fixes
- **Status:** Complete
- **Fixes:** parser.py VERIFIED tags, app.py tool integration, core.py list-content handling, pricing.py soru_uretici_pm, CLAUDE.md agent counts

### Shared Agent Runner (DEBT-1)
- **Status:** Complete
- **Location:** `shared/agent_runner.py`
- **Impact:** main.py and app.py now use shared runner — eliminated ~231 lines of duplication

### SKILL.md Domain Enrichment
- **Status:** Complete (56/56 files)
- **All 28 domains enriched** with real methodology, sanity checks, expert differentiation, standards, failure modes
- **Packages:** 5 batches committed (aerodinamik→termal, elektrik→optik, mekanik_tasarim→denizcilik, robotik→biyomedikal, cevre→uzay)

### Session Persistence (DEBT-6)
- **Status:** Complete
- **Location:** `shared/session_store.py`, `data/sessions.db`
- **Architecture:** SQLite-based (stdlib, zero deps), WAL mode, thread-safe
- **Features:**
  - Completed sessions survive server restarts (auto-restored on startup)
  - 5 checkpoint points during analysis (domain confirm, QA, each round, done, error)
  - API endpoints: GET/DELETE /api/sessions, GET /api/sessions/{sid}
  - Download endpoints fall back to SQLite when session not in memory
  - Streamlit sidebar shows past analyses, clickable to reload
  - Auto-cleanup of sessions older than 30 days
- **Blackboard serialization:** `to_dict()`/`from_dict()` added to `blackboard.py`

### Persistent Memory Layer
- **Status:** Complete
- **Location:** `memory/`, `skills/consolidate-memory/`
- **Files:** recent-memory.md, long-term-memory.md, project-memory.md

### Token Efficiency — 3 Improvements
- **Status:** COMPLETE
- **Branch:** `claude/add-skills-improve-caching-Yu7GY`
- **Goal:** Reduce token usage 15-40% on repeat/similar analyses
- **Improvement 1:** Unified RAG injection → `shared/rag_context.py` (NEW) — all 3 entry points now use shared functions
- **Improvement 2:** Structured parameter persistence → `blackboard.py` export_parameters() + `rag/store.py` parameters_json storage + retrieval
- **Improvement 3:** Template-based guidance → `rag/store.py` get_analysis_template() + final report injection via build_final_report_context()
- **Files modified:** blackboard.py, rag/store.py, shared/rag_context.py (new), main.py, app.py, orchestrator.py
- **Commits:** e6ad5e7, 428f76c, 86d2efe, 410b214, 7035e01, a6fdac9

### B2 — Shared Analysis Modes Module (DEBT-2)
- **Status:** COMPLETE
- **Branch:** `claude/add-skills-improve-caching-Yu7GY`
- **Goal:** Deduplicate ~1,700 lines of near-identical analysis logic across 3 entry points
- **Architecture:** Callback-based `AnalysisIO` dataclass + `FullLoopHooks` for entry-point specifics
- **New files:**
  - `shared/analysis_helpers.py` — `build_context_history()`, `update_blackboard()`, `extract_quality_score()`
  - `shared/analysis_modes.py` — `AnalysisIO`, `FullLoopHooks`, `run_single_analysis()`, `run_dual_analysis()`, `run_full_loop_analysis()`
- **Entry points now thin adapters:**
  - `main.py`: `_make_io()` method + 3-6 line adapter functions
  - `app.py`: `_make_app_io()` + hooks for quality gate (C5) + Streamlit round state
  - `orchestrator.py`: `_make_cli_io()` + AGENTS-dict-based model promotion
- **Net impact:** ~1,300 lines removed, ~600 added → ~700 lines eliminated
- **Commits:** 1141a61, 40ab564, 5f806d6, 82df186, (Commit 6 pending)

## Recent Changes

- [2026-04-10] B2: Shared analysis modes module — AnalysisIO/FullLoopHooks, ~700 lines eliminated across 3 entry points
- [2026-03-26] DEBT-6: Session persistence layer (SQLite, checkpoints, API endpoints, Streamlit sidebar)
- [2026-03-26] SKILL.md enrichment completed for all 56 files (28 domains × 2 experts)
- [2026-03-26] Shared agent_runner integration into main.py and app.py
- [2026-03-18] System integrity audit and fixes (parser, app.py tools, core.py, pricing, CLAUDE.md)
- [2026-03-18] Plan 2 Patch: 4-layer LLM tool calling quality improvements
- [2026-03-18] Tier 1 tool wrappers completed (25 tools)
- [2026-03-18] Created memory directory with three memory files

## Blocked Items

- Tier 2: PyANSYS (when license ready)
- Tier 3: MATLAB Engine API (when license ready)

## Architecture Notes

- 76 agents total: 56 domain (28 × 2) + 20 support
- Tool integration: core.py shared by orchestrator.py, main.py, and app.py
- All entry points now support solver tools via run_tool_loop()
- Agent execution: shared/agent_runner.py used by all 3 entry points
- Session persistence: shared/session_store.py → data/sessions.db (SQLite, WAL mode)
- Blackboard: fully serializable via to_dict()/from_dict() for session persistence
