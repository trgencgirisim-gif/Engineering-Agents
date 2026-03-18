---
name: consolidate-memory
description: Reads the past 24hrs of conversation logs from ~/.claude, extracts key decisions, preferences, and facts, updates the memory files accordingly, and promotes important facts and patterns from recent to long-term memory. Set up as a nightly scheduled task.
---

# Consolidate Memory Skill

This skill maintains the persistent memory layer by processing recent Claude Code conversation logs and updating the three memory files.

## What It Does

1. **Scans** `~/.claude/projects/` for conversation JSONL logs from the past 24 hours
2. **Extracts** key decisions, code changes, preferences, and patterns from assistant messages
3. **Updates** `memory/recent-memory.md` with new entries (removes entries older than 48hrs)
4. **Promotes** recurring patterns and important facts from recent -> `memory/long-term-memory.md`
5. **Updates** `memory/project-memory.md` with current branch state and work items

## How to Run

### Manual invocation
```bash
python skills/consolidate-memory/consolidate.py
```

### Scheduled nightly (cron)
```bash
# Add to crontab -e:
0 2 * * * cd /home/user/Engineering-Agents && python skills/consolidate-memory/consolidate.py >> /tmp/consolidate-memory.log 2>&1
```

### As a Claude Code hook (settings.json)
```json
{
  "hooks": {
    "SessionStart": [
      {
        "command": "python /home/user/Engineering-Agents/skills/consolidate-memory/consolidate.py --if-stale 12h",
        "timeout": 30000
      }
    ]
  }
}
```

## Memory File Locations

| File | Purpose | Retention |
|------|---------|-----------|
| `memory/recent-memory.md` | Rolling 48hr context | Auto-pruned |
| `memory/long-term-memory.md` | Distilled facts & patterns | Permanent |
| `memory/project-memory.md` | Active project state | Updated per session |

## Promotion Criteria (Recent -> Long-Term)

A fact or pattern is promoted when:
- It appears in 3+ separate sessions
- It represents a user preference or coding style choice
- It documents an architectural decision with rationale
- It captures a non-obvious workaround or known issue
