# Engineering Agents — TODO Tracker

This file tracks progress across sessions. Update status as tasks complete.
When resuming after an interruption, read this file first to continue.

---

## PLAN STATUS SUMMARY

| ID | Task | Status | Notes |
|----|------|--------|-------|
| A1-A6 | Port blackboard + features to main.py & orchestrator.py | DONE | Commit 2290934 |
| B1 | Shared agent_runner module (lib/agent_runner.py) | DONE | shared/agent_runner.py, commit e8eb119 |
| B2 | Shared analysis_modes module | NOT STARTED | High priority — dedup run_tekli/run_cift/run_full_loop |
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
| capytaine | denizcilik | IN PROGRESS (background agent) |
| rayoptics | optik | IN PROGRESS (background agent) |
| meep | optik | IN PROGRESS (background agent) |
| openmc | nukleer | IN PROGRESS (background agent) |
| openrocket | uzay, savunma | IN PROGRESS (background agent) |
| openfoam | aerodinamik, akiskan | IN PROGRESS (background agent) |
| openmodelica | hidrolik, sistem | IN PROGRESS (background agent) |
| freecad | uretim | IN PROGRESS (background agent) |
| dwsim | kimya | IN PROGRESS (background agent) |
| sumo | otomotiv | IN PROGRESS (background agent) |

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

1. Wait for background agents to finish tier1 wrappers (10 remaining)
2. B2: Shared analysis_modes module (dedup run_tekli/run_cift/run_full_loop)
3. Commit and push all changes

---

## SESSION LOG

- 2026-03-18 session 1: B3 completed (report/ package split). PyPSA tool added.
- 2026-03-18 session 2: Completed core.py wiring, C1 adaptive model porting,
  C3 streaming porting, tools.yaml activation (54 files), SKILL.md tool instructions
  (54 files), resilient tools/__init__.py. Background agents creating remaining
  tier1 wrappers.
