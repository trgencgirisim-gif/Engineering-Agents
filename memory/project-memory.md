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
- **Status:** In Progress
- **Branch:** `claude/add-skills-improve-caching-Yu7GY`
- **Goal:** Reduce token usage 15-40% on repeat/similar analyses
- **Improvement 1:** Unified RAG injection → `shared/rag_context.py` (NEW)
- **Improvement 2:** Structured parameter persistence → `blackboard.py` + `rag/store.py`
- **Improvement 3:** Template-based guidance → `rag/store.py` + final report injection
- **Files:** blackboard.py, rag/store.py, shared/rag_context.py (new), main.py, app.py, orchestrator.py

## Recent Changes

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
