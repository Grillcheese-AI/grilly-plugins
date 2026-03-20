---
name: user-profile
description: Manage your user profile — view, edit, delete observations, enable/disable, configure what gets tracked. Profile is global across all projects.
---

Manage the "know your user" profile. This feature silently observes user behavior,
emotions, goals, habits, and recurrent requests so Claude can adapt seamlessly.

## Privacy

- **Opt-in only** — disabled by default, must be explicitly enabled
- **100% local** — stored in `~/.elephant-coder/user_profile.db`, never leaves the machine
- **User controls everything** — view, edit, and delete any observation at any time
- **Global** — the user is the same person across all projects

## Usage

- `/ec:user-profile` — show full profile and stats
- `/ec:user-profile enable` — opt in to user profiling
- `/ec:user-profile disable` — opt out (preserves data, stops tracking)
- `/ec:user-profile delete` — delete specific observations or entire profile
- `/ec:user-profile categories` — show what gets tracked and why

## Steps

### Show profile
1. Call `get_user_profile()` to see all observations
2. Show them grouped by category with confidence indicators
3. Show recurrent request patterns with auto-eligibility status
4. Show stats from `memory_status()` (user profile section)

### Enable
1. Call `update_settings(user_profile_enabled=True)`
2. Confirm: "User profiling enabled. I'll silently observe patterns to adapt to you."
3. Explain what gets tracked (see categories below)

### Disable
1. Call `update_settings(user_profile_enabled=False)`
2. Confirm: "User profiling disabled. Existing data preserved — use `/ec:user-profile delete` to remove."

### Delete
Ask the user what to delete:
- A specific observation (by ID)
- A category (e.g., "delete all emotion observations")
- Everything (`delete_user_observation(delete_all=True)`)

### Categories
Show the user what gets tracked:

| Category | What | Why |
|----------|------|-----|
| `professional_goal` | Career objectives, project ambitions | Inform all technical suggestions |
| `personal_goal` | Life goals, values, motivations | Shape tone and priorities |
| `emotion` | Frustration, excitement, fatigue, focus | Adapt communication style |
| `habit` | Workflow patterns, schedule, coding style | Match working rhythm |
| `problem` | Recurring blockers, pain points | Proactively address issues |
| `victory` | Accomplishments, breakthroughs | Celebrate and build on success |
| `preference` | Tool choices, communication style | Respect preferences |
| `recurrent_request` | Things asked repeatedly | Automate after 3 occurrences |
| `personality` | Personality traits over time | Consistent interaction style |
| `expertise` | Areas of strength | Don't over-explain known topics |
| `growth` | Learning areas | Provide extra context when needed |

## How Observations Work

- Claude silently calls `observe_user()` when it notices patterns
- Repeated observations automatically increase confidence (Hebbian reinforcement)
- Stale observations (not seen in 90 days) decay in confidence
- Observations with confidence < 0.1 are effectively forgotten
- User's **objectives** (professional_goal, personal_goal) inform ALL suggestions

## Recurrent Request Automation

When a request pattern is seen 3+ times:
1. It becomes "auto-eligible"
2. Claude proactively performs the action before the user asks
3. The user can set a `suggested_action` for automation
4. Example: if user always says "run tests" after editing → Claude runs tests automatically
