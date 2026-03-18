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
- **Status:** In progress
- **Fixes:** parser.py VERIFIED tags, app.py tool integration, core.py list-content handling, pricing.py soru_uretici_pm, CLAUDE.md agent counts

### Persistent Memory Layer
- **Status:** Complete
- **Location:** `memory/`, `skills/consolidate-memory/`
- **Files:** recent-memory.md, long-term-memory.md, project-memory.md

## Recent Changes

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
