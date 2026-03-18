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
