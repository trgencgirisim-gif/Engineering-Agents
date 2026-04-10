# Recent Memory (Rolling 48hr Context)

> This file is automatically updated by the consolidate-memory skill.
> It captures decisions, actions, and context from the last 48 hours.
> Entries older than 48hrs are promoted to long-term-memory.md or discarded.

## Format

Each entry follows:
```
### [YYYY-MM-DD HH:MM] Topic
- **Decision/Action:** What was decided or done
- **Context:** Why it matters
- **Participants:** Who was involved (user, agent, etc.)
- **Status:** active | completed | superseded
```

---

## Entries

### [2026-04-10 12:00] B2 — Shared Analysis Modes Module COMPLETE
- **Decision/Action:** Extracted shared analysis logic from 3 entry points into `shared/analysis_modes.py` + `shared/analysis_helpers.py`. Created callback-based `AnalysisIO` dataclass + `FullLoopHooks` for entry-point specifics. Entry points are now thin adapters (3-15 lines each).
- **Key architecture decisions:**
  1. `AnalysisIO` holds callbacks: `run_agent`, `run_parallel`, `on_event`, `rag_store`, `checkpoint`, `get/set_domain_model`, `on_model_promote`
  2. `on_model_promote(keys)` returns a restore closure — handles both session-attribute (main.py) and AGENTS-dict (orchestrator.py) promotion styles
  3. `FullLoopHooks` carries optional app.py quality gate (C5) + Streamlit round state callbacks
  4. Prep phases (prompt engineering + domain selection) stay in entry points
- **Commits (6 total):** 1141a61 (helpers), 40ab564 (modes 1+2), 5f806d6 (full loop), 82df186 (app.py hooks), (commit 6 cleanup+memory pending)
- **Net impact:** ~700 lines eliminated across main.py/app.py/orchestrator.py
- **Status:** completed

### [2026-04-05 12:00] Token Efficiency — 3 Improvements COMPLETE
- **Decision/Action:** Implemented all 3 token efficiency improvements across 6 commits:
  1. `blackboard.py` — `export_parameters()` for structured param export
  2. `rag/store.py` — `parameters_json` storage, `get_parameters_for_domain()`, `get_analysis_template()`
  3. `shared/rag_context.py` — NEW shared module: `build_domain_message()`, `build_final_report_context()`, `build_prompt_engineer_message()`
  4. `main.py` — All 3 modes (tekli/cift/full_loop) now inject RAG into domain agents (Round 1) + final report
  5. `app.py` — Replaced ~40 lines of inline RAG with shared module calls
  6. `orchestrator.py` — All 3 modes now inject RAG, kaydet() passes parameters_json
- **Context:** All 3 entry points now consistently learn from past analyses. Expected 15-40% token savings on repeat/similar problems.
- **Status:** completed

### [2026-03-18 19:50] Caching System Improvements
- **Decision/Action:** Fixed 4 caching issues: (1) cache key now hashes full history content instead of just length, (2) upgraded from FIFO to LRU eviction via OrderedDict, (3) standardized prompt cache TTL to 1h across all entry points, (4) corrected Opus threshold comment (4096 not 2048)
- **Context:** Audit revealed cache key collisions when same message sent with different history of equal length; FIFO eviction was suboptimal; TTL was inconsistent (5min default vs 1h in app.py)
- **Status:** completed

### [2026-03-18 07:30] System Integrity Audit and Fixes
- **Decision/Action:** Ran full system audit; fixed 6 issues: parser.py VERIFIED tags, app.py tool integration, core.py list-content, pricing.py profile, CLAUDE.md counts, memory updates
- **Context:** Post Plan 2 Patch quality check to ensure all components are consistent
- **Status:** completed

### [2026-03-18 07:00] Plan 2 Patch — LLM Tool Calling Quality
- **Decision/Action:** Implemented 4-layer approach: (1) rewrote 25 tool descriptions, (2) added solver obligation blocks to 54 SKILL.md, (3) added few-shot examples for 5 critical domains, (4) added TOOL_REMINDER_PREFIX in core.py
- **Context:** LLMs were not consistently calling available solvers; these layers ensure obligation and provide examples
- **Status:** completed

### [2026-03-18 00:00] Memory System Initialized
- **Decision/Action:** Created persistent memory layer with three files
- **Context:** Enables cross-session context retention for Claude Code
- **Status:** completed
