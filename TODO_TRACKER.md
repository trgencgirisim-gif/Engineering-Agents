# Engineering Agents — TODO Tracker

This file tracks progress across sessions. Update status as tasks complete.
When resuming after an interruption, read this file first to continue.

---

## PLAN STATUS SUMMARY

| ID | Task | Status | Notes |
|----|------|--------|-------|
| A1-A6 | Port blackboard + features to main.py & orchestrator.py | DONE | Commit 2290934 |
| B1 | Shared agent_runner module (lib/agent_runner.py) | DONE | shared/agent_runner.py, commit e8eb119 |
| B2 | Shared analysis_modes module | DONE | shared/analysis_modes.py + analysis_helpers.py; ~700 lines eliminated; commits 1141a61, 40ab564, 5f806d6, 82df186, 7316339 |
| B3 | Split report_generator.py into report/ package | DONE | report/styles.py, charts.py, sections.py, builder.py |
| B4-B6 | Parser regex, blackboard caching, RAG improvements | DONE | Commit e8eb119 |
| C1 | Adaptive model selection | DONE | Ported to main.py + orchestrator.py |
| C2 | Incremental agent execution | DONE | |
| C3 | Streaming response | DONE | Ported to main.py + orchestrator.py |
| C4 | Smart context window | DONE | |
| C5 | Agent output quality gate (Haiku) | DONE | Commit fd2db8b |
| C6 | Cost prediction before analysis | DONE | Commit fd2db8b |
| P1 | Migrate agents_config to SKILL.md architecture | DONE | Commit 850b097 |

---

## TOOL INTEGRATION STATUS

### Tier1 Wrappers

| Tool Name | Domains | Status |
|-----------|---------|--------|
| cantera | yanma, termodinamik, kimya | DONE |
| coolprop | termodinamik, termal | DONE |
| fenics | termal, yapisal, dinamik, akiskan, insaat, mekanik_tasarim | DONE |
| materials_project | malzeme | DONE |
| matminer | malzeme | DONE |
| opensees | yapisal, dinamik, insaat | DONE |
| pybullet | robotik | DONE |
| pyspice | elektrik | DONE |
| python_control | kontrol, savunma | DONE |
| reliability | guvenilirlik | DONE |
| su2 | aerodinamik, uzay | DONE |
| pypsa | enerji | DONE |
| brightway2 | cevre | DONE |
| opensim | biyomedikal | DONE |
| febio | biyomedikal | DONE |
| capytaine | denizcilik | DONE |
| rayoptics | optik | DONE |
| meep | optik | DONE |
| openmc | nukleer | DONE |
| openrocket | uzay, savunma | DONE |
| openfoam | aerodinamik, akiskan | DONE |
| openmodelica | hidrolik, sistem | DONE |
| freecad | uretim | DONE |
| dwsim | kimya | DONE |
| sumo | otomotiv | DONE |

### Other Tool Integration

| Item | Status |
|------|--------|
| tools/__init__.py resilient auto-registration | DONE |
| core.py wired into main.py + orchestrator.py | DONE |
| scripts/update_skill_prompts.py | DONE |
| scripts/activate_tools.py | DONE |
| SKILL.md files have tool usage instructions (54/56) | DONE |
| tools.yaml active_tools activated (54/56) | DONE |

---

## REMAINING WORK

All PLAN.md items are complete. Only externally-blocked items remain:

1. Tier 2: PyANSYS (blocked on license)
2. Tier 3: MATLAB Engine API (blocked on license)

---

## SESSION LOG

- 2026-03-18 session 1: B3 completed (report/ package split). PyPSA tool added.
- 2026-03-18 session 2: Completed core.py wiring, C1 adaptive model porting,
  C3 streaming porting, tools.yaml activation (54 files), SKILL.md tool instructions
  (54 files), resilient tools/__init__.py. Background agents creating remaining
  tier1 wrappers.
- 2026-03-26 session: DEBT-6 session persistence (SQLite), shared agent_runner
  integration into main.py and app.py, SKILL.md enrichment for all 56 files,
  memory layer created.
- 2026-04-05 session: Token efficiency — 3 improvements (shared RAG context,
  parameter persistence, template-based guidance) across all 3 entry points.
- 2026-04-10 session: B2 shared analysis_modes module complete. AnalysisIO /
  FullLoopHooks callback pattern; ~700 lines eliminated across main.py/app.py/
  orchestrator.py. All 25 tier1 wrappers confirmed on disk. Dead helper
  methods removed from main.py.
