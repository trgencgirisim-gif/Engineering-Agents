# Engineering Multi-Agent Analysis System

## Memory Layer

**Always load at session start:**
- Read and inline `memory/recent-memory.md` — rolling 48hr context with recent decisions, actions, and state
- Reference `memory/long-term-memory.md` (path: `memory/long-term-memory.md`) — distilled facts, user preferences, recurring patterns. Consult when you need historical context or user preference recall.
- Reference `memory/project-memory.md` (path: `memory/project-memory.md`) — active branches, work items, and recent changes. Consult when resuming work or checking project state.

**Consolidation:** Run `python skills/consolidate-memory/consolidate.py` nightly or invoke `/consolidate-memory` to process recent conversation logs into the memory layer.

## Architecture Overview

Multi-agent engineering analysis platform orchestrating 76 AI agents across 28 engineering domains.

- **3 entry points:** `orchestrator.py` (CLI), `main.py` (FastAPI backend), `app.py` (Streamlit frontend)
- **56 domain agents:** 28 domains x 2 experts (_a = theoretical/rigorous, _b = practical/field)
- **20 support agents:** Observer, Final Report Writer, Prompt Engineer, Cross-Validator, Conflict Resolution, etc.
- **RAG:** ChromaDB with sentence-transformers (`all-MiniLM-L6-v2`) in `rag/store.py`
- **Reports:** Academic-style DOCX (IEEE/ASME) via `report_generator.py`

## Key Conventions

- **Turkish variable/function names** throughout: ajan=agent, mesaj=message, gecmis=history, maliyet=cost, yanit=response, cevap=answer, puan=score
- **Agent config structure:** `{isim, model, max_tokens, sistem_promptu, thinking_budget?}`
- **DOMAINS dict:** maps `"1"` → `("yanma", "Combustion")` etc. — defined in `config/domains.py`
- **Model pricing:** centralized in `config/pricing.py` — `get_rates(model)` returns `(r_in, r_out, r_cre, r_rd)`
- **All agent outputs must be in English** regardless of input language
- **Cost tracking** uses USD with TRY conversion via frankfurter.app API (1h cache)

## Running the Project

```bash
# FastAPI backend (serves static/index.html)
python main.py

# Streamlit frontend
streamlit run app.py

# CLI interactive mode
python orchestrator.py

# Basic API connectivity test
python test.py

# Install dependencies
pip install -r requirements.txt
```

**Environment:** Create `.env` with `ANTHROPIC_API_KEY=sk-ant-...`

## Analysis Modes

| Mode | Name | Description |
|------|------|-------------|
| 1 | Single (tekli) | Domain A experts only, cross-validation, observer, final report |
| 2 | Dual (cift) | A+B experts, conflict resolution, alternative scenarios |
| 3 | Semi-auto | User-interactive parameter extraction, domain confirmation |
| 4 | Full-auto | Multi-round iterative refinement, early exit at score >= 85/100 |

## Caching Strategy

### Anthropic Prompt Caching (2-block)
- **Block 1:** `CACHE_PREAMBLE` (~4175 tokens) — universal quality standards, shared by all agents. Cached with `{"type": "ephemeral"}`. Defined in `orchestrator.py`.
- **Block 2:** Agent-specific `sistem_promptu` — varies per agent. Cached separately with `{"type": "ephemeral"}`.
- This 2-block split ensures the preamble is cached once and reused across all 76 agents.
- Minimum cache thresholds: Sonnet 1024 tokens, Opus 4096 tokens.

### User Context Caching
- Large context blocks (>800 chars) sent with `cache_control: {"type": "ephemeral"}` in user messages.
- Enables reuse when the same accumulated output (`tum_ciktilar`) is sent to multiple agents.

### Local Result Cache
- Hash-based in-memory cache in `main.py` keyed on `(agent_key, message, history_length)`.
- Prevents redundant API calls for identical inputs. Skipped for thinking-mode agents.
- Max 200 entries, auto-evicts oldest.

### RAG Knowledge Base
- ChromaDB stores past analyses with metadata (quality_score, cost, domains, date).
- Semantic similarity retrieval via HNSW index (cosine distance < 0.65).
- Used to provide historical context to agents in subsequent analyses.

## Blackboard Architecture

### Overview
The Blackboard is a structured analysis state (`blackboard.py`) that sits between agents, enabling:
- **Selective context injection:** Each agent receives only relevant data (not the full `tum_ciktilar` blob)
- **Cross-domain flag routing:** Domain agents emit flags → parser extracts → blackboard stores → target domain receives in next round
- **Observer directive tracking:** Tracks which corrections were addressed vs ignored
- **Parameter convergence monitoring:** Detects oscillating values across rounds
- **Assumption consistency checking:** Cross-references assumptions between agents before observer evaluation

### Sections
| Section | Type | Description |
|---------|------|-------------|
| `parameters` | `Dict[str, List[Entry]]` | Numerical values with source agent, confidence, unit |
| `conflicts` | `List[dict]` | Agent disagreements, status: open/resolved |
| `assumptions` | `List[dict]` | Labeled assumptions from all agents |
| `cross_domain_flags` | `Dict[str, List[dict]]` | Issues indexed by target domain |
| `risk_register` | `List[dict]` | FMEA items with S/O/D/RPN |
| `open_questions` | `List[dict]` | Unanswered critical questions |
| `observer_directives` | `Dict[str, dict]` | Per-agent directives (FIX/ADD/CORRECT) |
| `round_history` | `List[dict]` | Per-round score and change summary |

### Key Methods
- `write(section, data, source_agent, round_num)` — thread-safe mutation
- `get_context_for(agent_key, round_num)` — returns ONLY relevant sections for that agent type
- `diff(round_a, round_b)` — parameter changes, resolved conflicts, score delta
- `to_summary()` — compact text for synthesis/final report
- `check_convergence()` — detects converging/oscillating/stable parameters
- `to_rag_metadata()` — structured data for RAG storage

### Parser (`parser.py`)
Hybrid regex + LLM (Haiku) fallback. Extracts structured data from agent outputs:
- Domain agents: parameters, cross-domain flags, assumptions
- Cross-validator: ERROR_[N], DATA_GAP_[N], BLOCKING_ISSUES
- Assumption inspector: ASSUMPTION_[N], UNCERTAINTY_[N], CONFLICT_ASSUMPTION_[N]
- Observer: KALİTE PUANI, per-agent directives, conflicts, early termination
- Risk agent: FMEA items with RPN values
- LLM fallback triggers when regex extracts < 30% of expected fields

### Data Flow with Blackboard
```
Round 1:
  Domain agents → parser → blackboard.parameters, .cross_domain_flags, .assumptions
  Validation agents ← blackboard.get_context_for("capraz_dogrulama") = parameter table + conflicts
  Observer ← blackboard.get_context_for("gozlemci") = full summary + directive status

Round 2+:
  Domain agents ← blackboard.get_context_for("yanma_a") = flags for yanma + observer directives + param diff
  After output → parser → blackboard updates + mark_directive_addressed()
  Validation ← updated blackboard context (selective)
  Observer ← full summary including directive tracking + assumption conflicts
```

## File Map

| File | Purpose |
|------|---------|
| `config/agents_config.py` | AGENTS + DESTEK_AJANLARI dicts (all 76 agent definitions with prompts) |
| `config/domains.py` | Shared DOMAINS dict (28 engineering domains) |
| `config/pricing.py` | Model pricing rates and cost calculation utility |
| `orchestrator.py` | CLI mode, CACHE_PREAMBLE definition, standalone `ajan_calistir()` |
| `main.py` | FastAPI backend, Session class, SSE streaming, local result cache |
| `app.py` | Streamlit frontend with dark theme, real-time agent streaming |
| `blackboard.py` | Blackboard class — structured analysis state with selective context injection |
| `parser.py` | Hybrid regex + LLM fallback parser for agent output extraction |
| `rag/store.py` | RAGStore class — save/query/delete analyses with ChromaDB |
| `report_generator.py` | Academic DOCX report generation (cover, abstract, findings, appendices) |
| `shared/analysis_helpers.py` | Extracted helpers: build_context_history, update_blackboard, extract_quality_score |
| `shared/analysis_modes.py` | Shared analysis modes: AnalysisIO, FullLoopHooks, run_single/dual/full_loop_analysis |
| `shared/rag_context.py` | Unified RAG context injection for all entry points |
| `static/index.html` | Web UI for FastAPI backend (vanilla JS, SSE client) |
| `memory/recent-memory.md` | Rolling 48hr context — inlined at session start |
| `memory/long-term-memory.md` | Distilled facts, preferences, patterns — referenced by path |
| `memory/project-memory.md` | Active project state, branches, work items |
| `skills/consolidate-memory/` | Nightly memory consolidation skill + script |

## Important Patterns

- **Parallel execution:** `ThreadPoolExecutor(max_workers=6)` for concurrent domain agent runs
- **Thread-safe cost tracking:** `threading.Lock` guards all cost/log mutations
- **Blackboard state:** Thread-safe structured state with per-agent selective context injection
- **Retry with backoff:** 5 attempts, 60s × attempt on rate limits (429)
- **Thinking mode:** Auto-fallback to non-thinking if API rejects the parameter
- **SSE streaming:** Real-time agent progress via Server-Sent Events (FastAPI mode)
- **Observer quality loop:** Scores 0-100; >= 85 triggers early termination in Mode 4
- **Smart agent skipping:** Score >= 90 skips GRUP C (risk + conflict); reduces cost
- **Cross-domain flag routing:** Parsed from domain outputs → stored on blackboard → injected into target domain agents in next round
- **Model optimization:** Haiku for low-stakes agents (domain_selector, ozet_ve_sunum, soru_uretici_pm)
