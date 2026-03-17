# Engineering Multi-Agent Analysis System

## Architecture Overview

Multi-agent engineering analysis platform orchestrating 78 AI agents across 28 engineering domains.

- **3 entry points:** `orchestrator.py` (CLI), `main.py` (FastAPI backend), `app.py` (Streamlit frontend)
- **56 domain agents:** 28 domains x 2 experts (_a = theoretical/rigorous, _b = practical/field)
- **22 support agents:** Observer, Final Report Writer, Prompt Engineer, Cross-Validator, Conflict Resolution, etc.
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
- This 2-block split ensures the preamble is cached once and reused across all 78 agents.
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

## File Map

| File | Purpose |
|------|---------|
| `config/agents_config.py` | AGENTS + DESTEK_AJANLARI dicts (all 78 agent definitions with prompts) |
| `config/domains.py` | Shared DOMAINS dict (28 engineering domains) |
| `config/pricing.py` | Model pricing rates and cost calculation utility |
| `orchestrator.py` | CLI mode, CACHE_PREAMBLE definition, standalone `ajan_calistir()` |
| `main.py` | FastAPI backend, Session class, SSE streaming, local result cache |
| `app.py` | Streamlit frontend with dark theme, real-time agent streaming |
| `rag/store.py` | RAGStore class — save/query/delete analyses with ChromaDB |
| `report_generator.py` | Academic DOCX report generation (cover, abstract, findings, appendices) |
| `static/index.html` | Web UI for FastAPI backend (vanilla JS, SSE client) |

## Important Patterns

- **Parallel execution:** `ThreadPoolExecutor(max_workers=6)` for concurrent domain agent runs
- **Thread-safe cost tracking:** `threading.Lock` guards all cost/log mutations
- **Retry with backoff:** 5 attempts, 60s × attempt on rate limits (429)
- **Thinking mode:** Auto-fallback to non-thinking if API rejects the parameter
- **SSE streaming:** Real-time agent progress via Server-Sent Events (FastAPI mode)
- **Observer quality loop:** Scores 0-100; >= 85 triggers early termination in Mode 4
- **Cross-domain flags:** Agents emit structured flags for issues outside their discipline
