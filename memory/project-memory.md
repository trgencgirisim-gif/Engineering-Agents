# Project Memory (Active Project State)

> Tracks the current state of active work items, branches, and in-flight changes.
> Updated by the consolidate-memory skill and during active sessions.

## Active Branches

| Branch | Purpose | Status |
|--------|---------|--------|
| `claude/add-skills-improve-caching-Yu7GY` | Skills system + caching improvements | in-progress |

## Current Work Items

### Tier 1 Tool Wrappers
- **Status:** In progress
- **Location:** `tools/tier1/`
- **Tools created:** opensim, febio, openmodelica, freecad, dwsim, sumo, brightway2
- **Script:** `scripts/update_skill_prompts.py` — scans tool wrappers, updates SKILL.md files

### Persistent Memory Layer
- **Status:** In progress
- **Location:** `memory/`, `skills/consolidate-memory/`
- **Files:** recent-memory.md, long-term-memory.md, project-memory.md

## Recent Changes

- [2026-03-18] Created memory directory with three memory files
- [2026-03-18] Building consolidate-memory skill

## Blocked Items

<!-- Items waiting on external input or dependencies -->

## Architecture Notes

<!-- Temporary architecture notes relevant to current work -->
