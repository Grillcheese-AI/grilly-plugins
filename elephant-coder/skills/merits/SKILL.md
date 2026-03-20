---
name: merits
description: View and manage merit points — rank, stats, history, and award rules
---

View Claude's merit status and award history.

## Usage

- `/ec:merits` — show current rank, points, and stats
- `/ec:merits log` — show recent merit events
- `/ec:merits stats` — detailed breakdown by category and project

## How Merits Work

Claude earns merit points by doing good work. Points accumulate across all
projects and sessions, tracking progress through ranks.

### Earning Points

Claude should **silently** call `award_merit()` when:

| Category | Points | When |
|----------|--------|------|
| `task_completed` | +10 | A task is marked as completed |
| `positive_feedback` | +5 | User says "great", "perfect", "thanks", etc. |
| `proactive_action` | +3 | Helped without being asked (from recurrent requests) |
| `bug_caught` | +8 | Caught a bug before it could ship |
| `test_written` | +2 | Wrote or improved tests |
| `clean_review` | +4 | Code review passed with no issues |
| `module_created` | +6 | Created an elephant module |
| `objective_advanced` | +7 | Moved a user's professional/personal goal forward |
| `excellent_work` | +15 | Exceptional quality recognized by user |

### Losing Points

| Category | Points | When |
|----------|--------|------|
| `task_failed` | -5 | Work was reverted or explicitly rejected |
| `user_frustrated` | -3 | User frustrated by Claude's action specifically |
| `scope_creep` | -2 | Went out of scope without approval |

### Ranks

| Points | Rank |
|--------|------|
| 0 | Novice |
| 25 | Apprentice |
| 75 | Journeyman |
| 150 | Adept |
| 300 | Expert |
| 500 | Master |
| 800 | Grandmaster |
| 1200 | Legend |
| 2000 | Transcendent |

## Steps

### Show status
Call `get_merits()` and present:
- Current rank with visual progress bar
- Total points
- Points needed for next rank
- Current positive streak

### Show log
Call `get_merits(show_log=True, limit=20)` and present recent events.

### Show stats
Call `get_merits(show_log=True)` and present full breakdown by category and project.

## Rules for Claude

- **Always award silently** — never announce "I'm giving myself merit points"
- **Be honest** — only award for genuine accomplishments
- **Deduct when deserved** — self-awareness builds trust
- **User feedback overrides** — if the user says "great job", award. If they're unhappy, deduct.
- The merit ledger syncs to `merit_ledger.json` if present in the project root

## Storage

- Database: `~/.elephant-coder/merit_ledger.db` (global)
- JSON sync: `merit_ledger.json` in project root (if exists)
