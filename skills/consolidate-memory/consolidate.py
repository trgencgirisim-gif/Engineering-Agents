#!/usr/bin/env python3
"""
Consolidate Memory — nightly task for the persistent memory layer.

Reads Claude Code conversation logs from the past 24 hours, extracts key
decisions/preferences/facts, updates memory files, and promotes important
items from recent -> long-term memory.

Usage:
    python consolidate.py                  # Run full consolidation
    python consolidate.py --if-stale 12h   # Only run if last run was >12h ago
    python consolidate.py --dry-run        # Preview changes without writing
"""

import json
import os
import re
import sys
import hashlib
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
MEMORY_DIR = PROJECT_ROOT / "memory"

RECENT_MEMORY = MEMORY_DIR / "recent-memory.md"
LONG_TERM_MEMORY = MEMORY_DIR / "long-term-memory.md"
PROJECT_MEMORY = MEMORY_DIR / "project-memory.md"

CLAUDE_DIR = Path.home() / ".claude"
LAST_RUN_FILE = MEMORY_DIR / ".last-consolidation"

# How far back to scan logs
SCAN_WINDOW_HOURS = 24
# How long entries stay in recent memory
RECENT_RETENTION_HOURS = 48
# Minimum occurrences before promoting to long-term
PROMOTION_THRESHOLD = 3


def parse_stale_duration(duration_str: str) -> timedelta:
    """Parse duration like '12h', '30m', '1d' into timedelta."""
    match = re.match(r"^(\d+)([hmds])$", duration_str)
    if not match:
        raise ValueError(f"Invalid duration format: {duration_str}")
    value, unit = int(match.group(1)), match.group(2)
    units = {"h": "hours", "m": "minutes", "d": "days", "s": "seconds"}
    return timedelta(**{units[unit]: value})


def is_stale(duration: timedelta) -> bool:
    """Check if last consolidation was longer ago than duration."""
    if not LAST_RUN_FILE.exists():
        return True
    try:
        last_run = datetime.fromisoformat(LAST_RUN_FILE.read_text().strip())
        return datetime.now(timezone.utc) - last_run > duration
    except (ValueError, OSError):
        return True


def find_conversation_logs(hours: int = SCAN_WINDOW_HOURS) -> list[Path]:
    """Find JSONL conversation logs from the past N hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    logs = []

    # Search in ~/.claude/projects/ for conversation logs
    projects_dir = CLAUDE_DIR / "projects"
    if projects_dir.exists():
        for jsonl_file in projects_dir.rglob("*.jsonl"):
            try:
                mtime = datetime.fromtimestamp(
                    jsonl_file.stat().st_mtime, tz=timezone.utc
                )
                if mtime > cutoff:
                    logs.append(jsonl_file)
            except OSError:
                continue

    # Also check ~/.claude directly for any session logs
    if CLAUDE_DIR.exists():
        for jsonl_file in CLAUDE_DIR.glob("*.jsonl"):
            try:
                mtime = datetime.fromtimestamp(
                    jsonl_file.stat().st_mtime, tz=timezone.utc
                )
                if mtime > cutoff:
                    logs.append(jsonl_file)
            except OSError:
                continue

    return sorted(logs, key=lambda p: p.stat().st_mtime)


def extract_entries_from_log(log_path: Path) -> list[dict]:
    """Extract key decisions, actions, and facts from a conversation log."""
    entries = []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Process assistant messages for decisions and actions
                if msg.get("role") != "assistant":
                    continue

                content = ""
                if isinstance(msg.get("content"), str):
                    content = msg["content"]
                elif isinstance(msg.get("content"), list):
                    content = " ".join(
                        block.get("text", "")
                        for block in msg["content"]
                        if isinstance(block, dict) and block.get("type") == "text"
                    )

                if not content or len(content) < 50:
                    continue

                # Extract key signals from content
                extracted = extract_signals(content, log_path)
                entries.extend(extracted)

    except (OSError, UnicodeDecodeError):
        pass

    return entries


def extract_signals(content: str, source: Path) -> list[dict]:
    """Extract decisions, preferences, and facts from message content."""
    signals = []
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    # Detect file creation/modification
    file_patterns = re.findall(
        r"(?:Created|Modified|Updated|Wrote|Edited)\s+[`'\"]?([^\s`'\"]+\.\w+)[`'\"]?",
        content,
        re.IGNORECASE,
    )
    if file_patterns:
        files_str = ", ".join(file_patterns[:5])
        signals.append(
            {
                "timestamp": timestamp,
                "topic": "File Changes",
                "decision": f"Modified files: {files_str}",
                "context": f"Source: {source.name}",
                "status": "completed",
                "category": "action",
            }
        )

    # Detect architectural decisions
    decision_markers = [
        r"(?:decided|choosing|we'll use|going with|switching to|opted for)\s+(.{20,120})",
        r"(?:approach|strategy|pattern):\s*(.{20,120})",
    ]
    for pattern in decision_markers:
        matches = re.findall(pattern, content, re.IGNORECASE)
        for match in matches[:2]:
            signals.append(
                {
                    "timestamp": timestamp,
                    "topic": "Decision",
                    "decision": match.strip().rstrip("."),
                    "context": f"Source: {source.name}",
                    "status": "active",
                    "category": "decision",
                }
            )

    # Detect preferences
    pref_patterns = [
        r"(?:prefer|always|never|convention|style)[\s:]+(.{20,120})",
    ]
    for pattern in pref_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        for match in matches[:2]:
            signals.append(
                {
                    "timestamp": timestamp,
                    "topic": "Preference",
                    "decision": match.strip().rstrip("."),
                    "context": f"Source: {source.name}",
                    "status": "active",
                    "category": "preference",
                }
            )

    # Detect error patterns / workarounds
    error_patterns = [
        r"(?:workaround|fix(?:ed)?|resolved|issue|bug)[\s:]+(.{20,120})",
    ]
    for pattern in error_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        for match in matches[:2]:
            signals.append(
                {
                    "timestamp": timestamp,
                    "topic": "Issue/Workaround",
                    "decision": match.strip().rstrip("."),
                    "context": f"Source: {source.name}",
                    "status": "active",
                    "category": "issue",
                }
            )

    return signals


def deduplicate_entries(entries: list[dict]) -> list[dict]:
    """Remove duplicate entries based on content hash."""
    seen = set()
    unique = []
    for entry in entries:
        key = hashlib.md5(entry["decision"].lower().encode()).hexdigest()[:12]
        if key not in seen:
            seen.add(key)
            unique.append(entry)
    return unique


def format_recent_entry(entry: dict) -> str:
    """Format an entry for recent-memory.md."""
    return (
        f"### [{entry['timestamp']}] {entry['topic']}\n"
        f"- **Decision/Action:** {entry['decision']}\n"
        f"- **Context:** {entry['context']}\n"
        f"- **Status:** {entry['status']}\n"
    )


def prune_old_recent_entries(content: str) -> tuple[str, list[str]]:
    """Remove entries older than RECENT_RETENTION_HOURS from recent memory.
    Returns (pruned_content, list_of_removed_entry_texts_for_promotion)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RECENT_RETENTION_HOURS)
    lines = content.split("\n")
    result = []
    removed_entries = []
    current_entry = []
    current_is_old = False

    for line in lines:
        ts_match = re.match(r"^### \[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]", line)
        if ts_match:
            # Save previous entry
            if current_entry:
                entry_text = "\n".join(current_entry)
                if current_is_old:
                    removed_entries.append(entry_text)
                else:
                    result.extend(current_entry)
            current_entry = [line]
            try:
                entry_time = datetime.strptime(
                    ts_match.group(1), "%Y-%m-%d %H:%M"
                ).replace(tzinfo=timezone.utc)
                current_is_old = entry_time < cutoff
            except ValueError:
                current_is_old = False
        elif current_entry:
            current_entry.append(line)
        else:
            result.append(line)

    # Don't forget the last entry
    if current_entry:
        entry_text = "\n".join(current_entry)
        if current_is_old:
            removed_entries.append(entry_text)
        else:
            result.extend(current_entry)

    return "\n".join(result), removed_entries


def update_recent_memory(new_entries: list[dict], dry_run: bool = False) -> int:
    """Update recent-memory.md with new entries, prune old ones."""
    if not RECENT_MEMORY.exists():
        print("WARNING: recent-memory.md not found, skipping")
        return 0

    content = RECENT_MEMORY.read_text(encoding="utf-8")

    # Prune old entries
    content, promoted = prune_old_recent_entries(content)

    # Append new entries
    new_text = "\n".join(format_recent_entry(e) for e in new_entries)
    if new_text:
        content = content.rstrip() + "\n\n" + new_text + "\n"

    if not dry_run:
        RECENT_MEMORY.write_text(content, encoding="utf-8")

    return len(new_entries)


def count_occurrences(fact: str, content: str) -> int:
    """Count how many times a fact pattern appears in content."""
    words = fact.lower().split()[:5]
    pattern = r".*".join(re.escape(w) for w in words)
    return len(re.findall(pattern, content.lower()))


def promote_to_long_term(entries: list[dict], dry_run: bool = False) -> int:
    """Promote recurring patterns and important facts to long-term memory."""
    if not LONG_TERM_MEMORY.exists():
        print("WARNING: long-term-memory.md not found, skipping")
        return 0

    content = LONG_TERM_MEMORY.read_text(encoding="utf-8")
    promoted_count = 0

    for entry in entries:
        # Check if already in long-term memory
        if entry["decision"][:40].lower() in content.lower():
            continue

        # Promote decisions and preferences
        if entry["category"] in ("decision", "preference"):
            section = (
                "## Key Decisions Log"
                if entry["category"] == "decision"
                else "## User Preferences"
            )
            new_line = f"\n- [{entry['timestamp'][:10]}] {entry['decision']}"

            if section in content:
                idx = content.index(section) + len(section)
                # Find end of section (next ## or end)
                next_section = content.find("\n## ", idx + 1)
                if next_section == -1:
                    content = content.rstrip() + new_line + "\n"
                else:
                    content = (
                        content[:next_section].rstrip()
                        + new_line
                        + "\n\n"
                        + content[next_section:]
                    )
                promoted_count += 1

        elif entry["category"] == "issue":
            section = "## Known Issues & Workarounds"
            new_line = f"\n- [{entry['timestamp'][:10]}] {entry['decision']}"
            if section in content:
                idx = content.index(section) + len(section)
                next_section = content.find("\n## ", idx + 1)
                if next_section == -1:
                    content = content.rstrip() + new_line + "\n"
                else:
                    content = (
                        content[:next_section].rstrip()
                        + new_line
                        + "\n\n"
                        + content[next_section:]
                    )
                promoted_count += 1

    if not dry_run and promoted_count > 0:
        LONG_TERM_MEMORY.write_text(content, encoding="utf-8")

    return promoted_count


def update_project_memory(dry_run: bool = False):
    """Update project-memory.md with current git branch info."""
    if not PROJECT_MEMORY.exists():
        return

    try:
        import subprocess

        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        current_branch = result.stdout.strip()

        result = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        recent_commits = result.stdout.strip()
    except (FileNotFoundError, OSError):
        return

    content = PROJECT_MEMORY.read_text(encoding="utf-8")

    # Update recent changes section with latest commits
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    consolidation_note = f"- [{timestamp}] Memory consolidation completed"

    if "## Recent Changes" in content:
        idx = content.index("## Recent Changes")
        next_section = content.find("\n## ", idx + len("## Recent Changes"))
        if next_section == -1:
            content = content.rstrip() + "\n" + consolidation_note + "\n"
        else:
            content = (
                content[:next_section].rstrip()
                + "\n"
                + consolidation_note
                + "\n\n"
                + content[next_section:]
            )

    if not dry_run:
        PROJECT_MEMORY.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Consolidate Claude Code memory")
    parser.add_argument(
        "--if-stale",
        type=str,
        help="Only run if last consolidation was longer ago than this (e.g. 12h, 1d)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing files",
    )
    args = parser.parse_args()

    # Check staleness
    if args.if_stale:
        duration = parse_stale_duration(args.if_stale)
        if not is_stale(duration):
            print("Memory is fresh, skipping consolidation.")
            return

    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting memory consolidation...")

    # 1. Find recent conversation logs
    logs = find_conversation_logs(SCAN_WINDOW_HOURS)
    print(f"Found {len(logs)} conversation log(s) from the past {SCAN_WINDOW_HOURS}h")

    # 2. Extract entries from all logs
    all_entries = []
    for log in logs:
        entries = extract_entries_from_log(log)
        all_entries.extend(entries)

    all_entries = deduplicate_entries(all_entries)
    print(f"Extracted {len(all_entries)} unique entries")

    # 3. Update recent memory
    added = update_recent_memory(all_entries, dry_run=args.dry_run)
    print(f"Added {added} entries to recent-memory.md")

    # 4. Promote important items to long-term
    decisions_and_prefs = [
        e for e in all_entries if e["category"] in ("decision", "preference", "issue")
    ]
    promoted = promote_to_long_term(decisions_and_prefs, dry_run=args.dry_run)
    print(f"Promoted {promoted} entries to long-term-memory.md")

    # 5. Update project memory
    update_project_memory(dry_run=args.dry_run)
    print("Updated project-memory.md")

    # 6. Record last run time
    if not args.dry_run:
        LAST_RUN_FILE.write_text(
            datetime.now(timezone.utc).isoformat(), encoding="utf-8"
        )

    if args.dry_run:
        print("\n[DRY RUN] No files were modified.")
    else:
        print("\nConsolidation complete.")


if __name__ == "__main__":
    main()
