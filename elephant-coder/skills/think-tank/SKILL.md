---
name: think-tank
description: Run multi-agent Think Tank sessions — assemble AI executives (CEO, CTO, Creative Director, etc.) for structured brainstorming, strategic planning, architecture reviews, and risk assessment. Native to elephant-coder, powered by OpenRouter.
---

Run a Think Tank session with AI executives who each bring a unique perspective.

## When to Use

- User faces a strategic decision or complex problem
- Multiple perspectives are needed (technical, business, creative, financial)
- Brainstorming new features or products
- Architecture decisions with trade-offs
- Risk assessment before a major change
- User asks for "brainstorm", "think tank", "get perspectives"

## Quick Start

```
1. start_think_tank(topic="Should we migrate to microservices?", template="architecture_review")
2. discuss_think_tank(meeting_id, "Our monolith is 50k LOC and deploy takes 20 min. Options?")
3. discuss_think_tank(meeting_id, "What about the migration risk?")
4. conclude_think_tank(meeting_id, decisions=["Phase 1: extract auth service"], next_steps=["Create RFC", "Prototype auth service"])
```

## Steps

### 1. Gather context
Before starting, pull elephant-coder context:
- `project_overview()` — current project state
- `get_tasks()` — active work
- `get_user_profile()` — user's goals

### 2. Pick the right template

| Template | Best For | Participants |
|----------|----------|-------------|
| `strategic_planning` | Business direction, priorities | CEO, CTO, Finance, Product |
| `product_innovation` | New features/products | Product, Creative, CTO, Research |
| `architecture_review` | Tech decisions, trade-offs | CTO, Research, Product |
| `risk_assessment` | Risk analysis, mitigation | Finance, CEO, CTO, Research |
| `brainstorm` | Open exploration (default) | All 6 executives |

### 3. Start and facilitate
Call `start_think_tank()` with the topic. Then use `discuss_think_tank()` to:
- Send the initial brief (include elephant-coder context)
- Ask follow-up questions
- Request specifics ("CTO, what's the migration path?")
- Challenge assumptions ("Research, what data supports this?")

### 4. Conclude and apply
Call `conclude_think_tank()` with decisions and next steps.
Then:
- Create tasks with `add_task()` for each next step
- Record key decisions with `take_note()`
- Award merit points for running the session

## AI Executives

| Executive | Perspective | Asks |
|-----------|------------|------|
| CEO_Strategic | Business strategy, market position | "What's the ROI?" |
| CTO_Innovation | Technical feasibility, architecture | "Can we prototype this?" |
| Creative_Director | Design thinking, novel approaches | "What if we tried...?" |
| Research_Lead | Data-driven, evidence-based | "What does the data say?" |
| Product_Strategist | User needs, product-market fit | "Who is this for?" |
| Finance_Analyst | Financial viability, risk | "Can we afford this?" |

## Requirements

- OpenRouter API key (same as ensemble mode) — set via `/ec:configure`
- No external services needed — runs natively in elephant-coder
