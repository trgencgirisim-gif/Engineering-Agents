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
