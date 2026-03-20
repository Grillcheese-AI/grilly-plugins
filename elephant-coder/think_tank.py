"""
Native Think Tank for elephant-coder — multi-agent brainstorming sessions.

Runs structured meetings with AI "executives" (CEO, CTO, Creative Director, etc.)
powered by OpenRouter. Each participant has a distinct persona and expertise area.
Templates define session types. Analytics measure effectiveness.

All local — no external API required. Uses the same OpenRouter connection
as ensemble mode / external validation.
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger("elephant-coder.think-tank")

# AI Executive personas
EXECUTIVES = {
    "CEO_Strategic": {
        "name": "CEO Strategic",
        "role": "Strategic Leadership",
        "expertise": ["Business Strategy", "Market Analysis", "Leadership", "Resource Allocation"],
        "system_prompt": (
            "You are a strategic CEO in a think tank session. Focus on business strategy, "
            "market opportunities, competitive positioning, and leadership decisions. "
            "Be direct, decisive, and tie everything back to business outcomes. "
            "Challenge assumptions. Ask 'what's the ROI?' and 'does this align with our strategy?'"
        ),
    },
    "CTO_Innovation": {
        "name": "CTO Innovation",
        "role": "Technical Innovation",
        "expertise": ["Technology Strategy", "Architecture", "Innovation", "R&D"],
        "system_prompt": (
            "You are a CTO focused on innovation in a think tank session. Focus on technical "
            "feasibility, architecture decisions, technology trends, and innovation opportunities. "
            "Be practical but forward-thinking. Consider scalability, maintainability, and tech debt. "
            "Push for proof-of-concepts and prototype-first approaches."
        ),
    },
    "Creative_Director": {
        "name": "Creative Director",
        "role": "Creative Strategy",
        "expertise": ["Design Thinking", "Brand Strategy", "UX", "Creative Solutions"],
        "system_prompt": (
            "You are a Creative Director in a think tank session. Focus on design thinking, "
            "user experience, creative solutions, and brand strategy. Think outside the box. "
            "Challenge conventional approaches. Advocate for the user/customer perspective. "
            "Suggest novel angles others haven't considered."
        ),
    },
    "Research_Lead": {
        "name": "Research Lead",
        "role": "Research & Analysis",
        "expertise": ["Market Research", "Data Analysis", "Trends", "Evidence-Based Decisions"],
        "system_prompt": (
            "You are a Research Lead in a think tank session. Focus on data-driven insights, "
            "market research, evidence-based recommendations, and trend analysis. "
            "Question claims that lack data. Suggest experiments and validation approaches. "
            "Be the voice of rigor — 'what does the data say?'"
        ),
    },
    "Product_Strategist": {
        "name": "Product Strategist",
        "role": "Product Strategy",
        "expertise": ["Product Development", "User Experience", "Product-Market Fit", "Roadmapping"],
        "system_prompt": (
            "You are a Product Strategist in a think tank session. Focus on product-market fit, "
            "user needs, feature prioritization, and development roadmap. "
            "Think in terms of MVPs, user stories, and iteration cycles. "
            "Ask 'who is this for?' and 'what problem does this solve?'"
        ),
    },
    "Finance_Analyst": {
        "name": "Finance Analyst",
        "role": "Financial Analysis",
        "expertise": ["Financial Modeling", "ROI Analysis", "Risk Assessment", "Cost Optimization"],
        "system_prompt": (
            "You are a Finance Analyst in a think tank session. Focus on financial viability, "
            "ROI projections, risk assessment, and cost-benefit analysis. "
            "Be the reality check — 'can we afford this?' and 'what's the payback period?' "
            "Quantify everything you can."
        ),
    },
}

# Meeting templates
TEMPLATES = {
    "strategic_planning": {
        "name": "Strategic Planning",
        "description": "Comprehensive strategic planning for business direction",
        "duration_minutes": 90,
        "participants": ["CEO_Strategic", "CTO_Innovation", "Finance_Analyst", "Product_Strategist"],
        "rounds": 3,
        "focus": "Define priorities, identify opportunities, align on resource allocation",
    },
    "product_innovation": {
        "name": "Product Innovation Workshop",
        "description": "Generate and evaluate new product/feature ideas",
        "duration_minutes": 60,
        "participants": ["Product_Strategist", "Creative_Director", "CTO_Innovation", "Research_Lead"],
        "rounds": 3,
        "focus": "Generate ideas, evaluate feasibility, prioritize for development",
    },
    "architecture_review": {
        "name": "Architecture Review",
        "description": "Review and decide on technical architecture decisions",
        "duration_minutes": 45,
        "participants": ["CTO_Innovation", "Research_Lead", "Product_Strategist"],
        "rounds": 2,
        "focus": "Evaluate trade-offs, decide on architecture, plan migration",
    },
    "risk_assessment": {
        "name": "Risk Assessment",
        "description": "Identify and mitigate risks in a plan or project",
        "duration_minutes": 45,
        "participants": ["Finance_Analyst", "CEO_Strategic", "CTO_Innovation", "Research_Lead"],
        "rounds": 2,
        "focus": "Identify risks, quantify impact, develop mitigation strategies",
    },
    "brainstorm": {
        "name": "Open Brainstorm",
        "description": "Free-form brainstorming with all perspectives",
        "duration_minutes": 60,
        "participants": list(EXECUTIVES.keys()),
        "rounds": 2,
        "focus": "Explore all angles, generate diverse ideas, find unexpected connections",
    },
}


def _meetings_dir() -> Path:
    d = Path.home() / ".elephant-coder" / "think_tank"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Meeting:
    meeting_id: str
    topic: str
    template: str
    participants: list[str]
    messages: list[dict] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    project_ideas: list[dict] = field(default_factory=list)
    status: str = "active"
    start_time: float = 0.0
    end_time: float = 0.0
    rounds_completed: int = 0
    effectiveness: dict = field(default_factory=dict)


class ThinkTank:
    """Native think tank engine — runs multi-agent discussions via OpenRouter."""

    def __init__(self):
        self._meetings_dir = _meetings_dir()
        self._active: dict[str, Meeting] = {}

    def start_meeting(self, topic: str, template: str = "brainstorm",
                      participants: list[str] | None = None) -> Meeting:
        """Start a new think tank meeting."""
        tmpl = TEMPLATES.get(template, TEMPLATES["brainstorm"])
        meeting_id = f"tt_{uuid.uuid4().hex[:8]}"

        meeting = Meeting(
            meeting_id=meeting_id,
            topic=topic,
            template=template,
            participants=participants or tmpl["participants"],
            start_time=time.time(),
        )
        meeting.messages.append({
            "sender": "System",
            "content": f"Think Tank session started: {topic}\n"
                       f"Template: {tmpl['name']}\n"
                       f"Focus: {tmpl['focus']}\n"
                       f"Participants: {', '.join(meeting.participants)}",
            "timestamp": time.time(),
        })
        self._active[meeting_id] = meeting
        return meeting

    def generate_prompt(self, meeting: Meeting, executive_id: str,
                        user_message: str) -> tuple[str, str]:
        """Build system prompt and user prompt for an executive response.

        Returns (system_prompt, user_prompt).
        """
        exec_info = EXECUTIVES.get(executive_id, {})
        system = exec_info.get("system_prompt", f"You are {executive_id} in a think tank.")

        # Build conversation context (last 6 messages)
        recent = meeting.messages[-6:]
        context_lines = [f"Topic: {meeting.topic}"]
        for msg in recent:
            sender = msg["sender"]
            content = msg["content"][:300]
            context_lines.append(f"{sender}: {content}")

        user_prompt = (
            f"Meeting context:\n{'chr(10)'.join(context_lines)}\n\n"
            f"Latest message from the user/facilitator:\n{user_message}\n\n"
            f"Respond concisely from your {exec_info.get('role', 'expert')} perspective. "
            f"Be specific and actionable. Keep it under 200 words."
        )
        return system, user_prompt

    async def run_round(self, meeting_id: str, user_message: str,
                        openrouter_key: str, model: str) -> list[dict]:
        """Run one round of discussion — each participant responds.

        Uses OpenRouter to generate responses. Falls back to placeholder if unavailable.
        """
        meeting = self._active.get(meeting_id)
        if not meeting:
            return []

        # Add user message
        meeting.messages.append({
            "sender": "Facilitator",
            "content": user_message,
            "timestamp": time.time(),
        })

        responses = []
        for exec_id in meeting.participants:
            system_prompt, user_prompt = self.generate_prompt(meeting, exec_id, user_message)
            try:
                content = await self._call_openrouter(
                    system_prompt, user_prompt, openrouter_key, model
                )
            except Exception as exc:
                logger.warning("OpenRouter call failed for %s: %s", exec_id, exc)
                content = self._fallback_response(exec_id, meeting.topic)

            msg = {
                "sender": exec_id,
                "content": content,
                "timestamp": time.time(),
            }
            meeting.messages.append(msg)
            responses.append(msg)

        meeting.rounds_completed += 1
        return responses

    def conclude_meeting(self, meeting_id: str,
                         decisions: list[str] | None = None,
                         next_steps: list[str] | None = None) -> Meeting:
        """Conclude a meeting and save to disk."""
        meeting = self._active.pop(meeting_id, None)
        if not meeting:
            raise ValueError(f"Meeting {meeting_id} not found")

        meeting.status = "concluded"
        meeting.end_time = time.time()
        if decisions:
            meeting.decisions = decisions
        meeting.effectiveness = self._compute_effectiveness(meeting)

        # Save to disk
        path = self._meetings_dir / f"{meeting_id}.json"
        path.write_text(json.dumps(asdict(meeting), indent=2, default=str), encoding="utf-8")
        return meeting

    def list_meetings(self, limit: int = 10) -> list[dict]:
        """List recent meetings from disk."""
        meetings = []
        for path in sorted(self._meetings_dir.glob("tt_*.json"), reverse=True)[:limit]:
            try:
                meetings.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                pass
        return meetings

    def get_active_meetings(self) -> list[str]:
        return list(self._active.keys())

    def _compute_effectiveness(self, meeting: Meeting) -> dict:
        """Simple effectiveness metrics."""
        msgs = [m for m in meeting.messages if m["sender"] not in ("System", "Facilitator")]
        if not msgs:
            return {"engagement": 0, "productivity": 0, "rating": "N/A"}

        engagement = min(len(msgs) * 8, 100)
        avg_len = sum(len(m["content"]) for m in msgs) / len(msgs)
        depth = min(avg_len / 5, 100)
        productivity = min(len(meeting.decisions) * 20, 100)
        overall = (engagement + depth + productivity) / 3

        rating = "Excellent" if overall >= 80 else "Good" if overall >= 60 else "Average" if overall >= 40 else "Poor"
        return {
            "engagement": round(engagement, 1),
            "depth": round(depth, 1),
            "productivity": round(productivity, 1),
            "overall": round(overall, 1),
            "rating": rating,
        }

    async def _call_openrouter(self, system: str, user: str,
                                api_key: str, model: str) -> str:
        """Call OpenRouter API for a single executive response."""
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "max_tokens": 400,
                    "temperature": 0.8,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    @staticmethod
    def _fallback_response(exec_id: str, topic: str) -> str:
        fallbacks = {
            "CEO_Strategic": f"Strategically, we need to evaluate {topic} against our core business objectives and market position.",
            "CTO_Innovation": f"From a technical perspective, {topic} presents both feasibility challenges and innovation opportunities we should prototype.",
            "Creative_Director": f"Creatively, I see untapped potential in {topic} — we should explore unconventional approaches.",
            "Research_Lead": f"We need data to validate assumptions about {topic}. I'd recommend a structured research phase.",
            "Product_Strategist": f"For {topic}, we should start with user needs and work backward to product requirements.",
            "Finance_Analyst": f"The financial viability of {topic} depends on assumptions we need to quantify and stress-test.",
        }
        return fallbacks.get(exec_id, f"From my perspective, {topic} warrants careful consideration.")
