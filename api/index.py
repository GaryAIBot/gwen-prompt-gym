import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib import error, request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, desc, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

APP_NAME = "Gwen Prompt Gym"
LEVEL_SIZE = 140


class Base(DeclarativeBase):
    pass


class LearnerProfile(Base):
    __tablename__ = "learner_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    display_name: Mapped[str] = mapped_column(String(80), default="Learner")
    xp: Mapped[int] = mapped_column(Integer, default=0)
    streak: Mapped[int] = mapped_column(Integer, default=0)
    last_completed_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ScenarioTask(Base):
    __tablename__ = "scenario_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    domain: Mapped[str] = mapped_column(String(40))
    skill_focus: Mapped[str] = mapped_column(String(60))
    level_min: Mapped[int] = mapped_column(Integer, default=1)
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    xp_reward: Mapped[int] = mapped_column(Integer, default=30)
    prompt_brief: Mapped[str] = mapped_column(Text)
    learner_goal: Mapped[str] = mapped_column(Text)
    reflection_hint: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    attempts: Mapped[list["PromptAttempt"]] = relationship(back_populates="task")


class PromptAttempt(Base):
    __tablename__ = "prompt_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("scenario_tasks.id"))
    prompt_text: Mapped[str] = mapped_column(Text)
    reflection_text: Mapped[str] = mapped_column(Text)
    outcome_fit: Mapped[int] = mapped_column(Integer, default=3)
    clarity_rating: Mapped[int] = mapped_column(Integer, default=3)
    structure_rating: Mapped[int] = mapped_column(Integer, default=3)
    strategic_rating: Mapped[int] = mapped_column(Integer, default=3)
    confidence_after: Mapped[int] = mapped_column(Integer, default=3)
    improvement_focus: Mapped[str] = mapped_column(String(80), default="clarity")
    xp_awarded: Mapped[int] = mapped_column(Integer, default=0)
    coach_summary: Mapped[str] = mapped_column(Text)
    coach_tweaks: Mapped[str] = mapped_column(Text)
    revised_prompt: Mapped[str] = mapped_column(Text)
    badge_unlocked: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    task: Mapped[ScenarioTask] = relationship(back_populates="attempts")


class BadgeAward(Base):
    __tablename__ = "badge_awards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    label: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DailyRecommendation(Base):
    __tablename__ = "daily_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day_key: Mapped[str] = mapped_column(String(20), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("scenario_tasks.id"))
    rationale: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="heuristic")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./gwen_prompt_gym.db").strip().strip('"').strip("'")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
if DATABASE_URL.startswith("postgresql+psycopg://"):
    split_url = urlsplit(DATABASE_URL)
    query_items = []
    for key, value in parse_qsl(split_url.query, keep_blank_values=True):
        query_items.append(("sslmode", value) if key == "ssl" else (key, value))
    DATABASE_URL = urlunsplit((split_url.scheme, split_url.netloc, split_url.path, urlencode(query_items), split_url.fragment))

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)

app = FastAPI(title=APP_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


SCENARIOS = [
    {
        "slug": "exec-update-calm",
        "title": "Turn a messy status ask into a sharp executive update",
        "domain": "strategy",
        "skill_focus": "clarity",
        "level_min": 1,
        "difficulty": 1,
        "xp_reward": 30,
        "prompt_brief": "You need AI help drafting a concise executive update about a delayed initiative with political sensitivity.",
        "learner_goal": "Get a response that is clear, calm, and useful for leadership without sounding defensive.",
        "reflection_hint": "Notice whether your prompt gave enough context, audience framing, tone constraints, and output structure.",
    },
    {
        "slug": "decision-options",
        "title": "Ask AI for decision options, not just one answer",
        "domain": "management",
        "skill_focus": "option design",
        "level_min": 1,
        "difficulty": 1,
        "xp_reward": 30,
        "prompt_brief": "You are weighing 3 possible team priorities for the next quarter and want AI to frame the tradeoffs.",
        "learner_goal": "Elicit options, tradeoffs, and a recommendation logic rather than generic advice.",
        "reflection_hint": "Did your prompt force the AI to surface assumptions and compare options explicitly?",
    },
    {
        "slug": "feedback-conversation",
        "title": "Prepare for a hard but fair feedback conversation",
        "domain": "leadership",
        "skill_focus": "audience awareness",
        "level_min": 1,
        "difficulty": 2,
        "xp_reward": 36,
        "prompt_brief": "You want AI help preparing language for a feedback discussion with a strong but defensive colleague.",
        "learner_goal": "Get wording that is direct, respectful, and practical instead of vague or over-softened.",
        "reflection_hint": "Check whether your prompt gave enough interpersonal context and a clear desired tone.",
    },
    {
        "slug": "meeting-brief",
        "title": "Create a leadership meeting brief with sharper structure",
        "domain": "management",
        "skill_focus": "structure",
        "level_min": 2,
        "difficulty": 2,
        "xp_reward": 40,
        "prompt_brief": "You need AI help shaping a short meeting brief for a cross-functional leadership discussion.",
        "learner_goal": "Produce an output with a clear structure: purpose, context, options, recommendation, and open questions.",
        "reflection_hint": "Did you ask for a concrete output format or leave structure to chance?",
    },
    {
        "slug": "board-risk-note",
        "title": "Prompt for a risk note that leadership can act on",
        "domain": "strategy",
        "skill_focus": "strategic judgment",
        "level_min": 2,
        "difficulty": 3,
        "xp_reward": 45,
        "prompt_brief": "You need AI to help write a short note on a strategic risk that deserves leadership attention.",
        "learner_goal": "Elicit signal, impact, and decision relevance instead of generic risk language.",
        "reflection_hint": "Did the prompt push the AI toward prioritization and implications, not just description?",
    },
    {
        "slug": "delegate-better",
        "title": "Write a prompt for delegation support, not micromanagement",
        "domain": "leadership",
        "skill_focus": "constraints",
        "level_min": 2,
        "difficulty": 2,
        "xp_reward": 42,
        "prompt_brief": "You want AI help framing a delegated task so the other person gets clarity and ownership.",
        "learner_goal": "Get an output that defines success, guardrails, and check-ins without prescribing every step.",
        "reflection_hint": "Check whether your prompt distinguished outcomes, constraints, and autonomy.",
    },
    {
        "slug": "stakeholder-map",
        "title": "Make AI think like a stakeholder strategist",
        "domain": "strategy",
        "skill_focus": "context depth",
        "level_min": 3,
        "difficulty": 3,
        "xp_reward": 50,
        "prompt_brief": "You need AI help analyzing a stakeholder landscape before a contentious change initiative.",
        "learner_goal": "Get a nuanced mapping of interests, risks, likely resistance, and engagement moves.",
        "reflection_hint": "Did your prompt include political context and ask for differentiated stakeholder handling?",
    },
    {
        "slug": "team-retro",
        "title": "Design a smarter retrospective prompt",
        "domain": "management",
        "skill_focus": "learning loop",
        "level_min": 3,
        "difficulty": 3,
        "xp_reward": 48,
        "prompt_brief": "You want AI to suggest a retrospective format after a rough project cycle.",
        "learner_goal": "Get a format that surfaces patterns, tensions, and concrete experiments rather than bland lessons learned.",
        "reflection_hint": "Did you push for diagnosis and next-step quality, not just a facilitation template?",
    },
]

BADGES = [
    {"code": "first_rep", "label": "First Rep", "description": "Completed the first prompt workout."},
    {"code": "three_day_streak", "label": "Three-Day Streak", "description": "Completed prompt workouts on three consecutive days."},
    {"code": "clarity_builder", "label": "Clarity Builder", "description": "Completed two reps focused on clarity and structure."},
    {"code": "strategy_lens", "label": "Strategy Lens", "description": "Completed three strategy-domain scenarios."},
    {"code": "reflective_operator", "label": "Reflective Operator", "description": "Wrote high-quality reflections in three different reps."},
]


class CompleteAttemptIn(BaseModel):
    task_id: int
    prompt_text: str = Field(min_length=20, max_length=5000)
    reflection_text: str = Field(min_length=20, max_length=2500)
    outcome_fit: int = Field(ge=1, le=5)
    clarity_rating: int = Field(ge=1, le=5)
    structure_rating: int = Field(ge=1, le=5)
    strategic_rating: int = Field(ge=1, le=5)
    confidence_after: int = Field(ge=1, le=5)
    improvement_focus: str = Field(min_length=3, max_length=80)


class RefreshTaskIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)


@dataclass
class RecommendationResult:
    task: ScenarioTask
    rationale: str
    source: str


@dataclass
class CoachingResult:
    summary: str
    tweaks: str
    revised_prompt: str
    source: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def current_day_key() -> str:
    return utc_now().date().isoformat()


def level_from_xp(xp: int) -> int:
    return max(1, (xp // LEVEL_SIZE) + 1)


def progress_in_level(xp: int) -> dict[str, int]:
    level = level_from_xp(xp)
    base = (level - 1) * LEVEL_SIZE
    return {"level": level, "current": xp - base, "needed": LEVEL_SIZE}


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    seed_data()


def seed_data() -> None:
    with SessionLocal() as session:
        if not session.get(LearnerProfile, 1):
            session.add(LearnerProfile(id=1))
        existing = {slug for (slug,) in session.execute(select(ScenarioTask.slug)).all()}
        for item in SCENARIOS:
            if item["slug"] not in existing:
                session.add(ScenarioTask(**item))
        session.commit()


def serialize_task(task: ScenarioTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "slug": task.slug,
        "title": task.title,
        "domain": task.domain,
        "skillFocus": task.skill_focus,
        "levelMin": task.level_min,
        "difficulty": task.difficulty,
        "xpReward": task.xp_reward,
        "promptBrief": task.prompt_brief,
        "learnerGoal": task.learner_goal,
        "reflectionHint": task.reflection_hint,
    }


def serialize_attempt(attempt: PromptAttempt, task: ScenarioTask) -> dict[str, Any]:
    return {
        "id": attempt.id,
        "taskTitle": task.title,
        "domain": task.domain,
        "promptText": attempt.prompt_text,
        "reflectionText": attempt.reflection_text,
        "outcomeFit": attempt.outcome_fit,
        "clarityRating": attempt.clarity_rating,
        "structureRating": attempt.structure_rating,
        "strategicRating": attempt.strategic_rating,
        "confidenceAfter": attempt.confidence_after,
        "improvementFocus": attempt.improvement_focus,
        "xpAwarded": attempt.xp_awarded,
        "coachSummary": attempt.coach_summary,
        "coachTweaks": attempt.coach_tweaks,
        "revisedPrompt": attempt.revised_prompt,
        "badgeUnlocked": attempt.badge_unlocked,
        "createdAt": attempt.created_at.isoformat(),
    }


def summarize_history(session: Session, limit: int = 8) -> list[dict[str, Any]]:
    rows = session.execute(
        select(PromptAttempt, ScenarioTask)
        .join(ScenarioTask, PromptAttempt.task_id == ScenarioTask.id)
        .order_by(desc(PromptAttempt.created_at))
        .limit(limit)
    ).all()
    history = []
    for attempt, task in rows:
        history.append(
            {
                "task_title": task.title,
                "domain": task.domain,
                "skill_focus": task.skill_focus,
                "outcome_fit": attempt.outcome_fit,
                "clarity_rating": attempt.clarity_rating,
                "structure_rating": attempt.structure_rating,
                "strategic_rating": attempt.strategic_rating,
                "confidence_after": attempt.confidence_after,
                "improvement_focus": attempt.improvement_focus,
                "reflection_text": attempt.reflection_text,
            }
        )
    return history


def heuristic_recommendation(session: Session, profile: LearnerProfile) -> RecommendationResult:
    level = level_from_xp(profile.xp)
    tasks = session.execute(
        select(ScenarioTask).where(ScenarioTask.active.is_(True), ScenarioTask.level_min <= level + 1)
    ).scalars().all()
    if not tasks:
        raise HTTPException(status_code=500, detail="No scenario tasks available")

    history = summarize_history(session, limit=12)
    recent_titles = {item["task_title"] for item in history[:3]}
    focus_counts = Counter(item["improvement_focus"] for item in history)
    weak_domains = Counter(item["domain"] for item in history if item["outcome_fit"] <= 3 or item["strategic_rating"] <= 3)

    def score(task: ScenarioTask) -> float:
        value = float(task.xp_reward)
        value += 10 if task.level_min == level else 0
        value += weak_domains.get(task.domain, 0) * 8
        value += focus_counts.get(task.skill_focus, 0) * 5
        value -= 18 if task.title in recent_titles else 0
        value += task.difficulty * 2
        return value

    best = max(tasks, key=score)
    rationale = f"Picked to match level {level} while targeting domains and prompt skills that still look uneven in your recent reflections."
    return RecommendationResult(task=best, rationale=rationale, source="heuristic")


def call_openai(payload: dict[str, Any]) -> dict[str, Any] | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    req = request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def extract_output_text(data: dict[str, Any]) -> str | None:
    output = data.get("output")
    if not isinstance(output, list):
        return data.get("output_text")
    for item in output:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    return data.get("output_text")


def llm_recommendation(session: Session, profile: LearnerProfile) -> RecommendationResult | None:
    level = level_from_xp(profile.xp)
    candidates = session.execute(
        select(ScenarioTask).where(ScenarioTask.active.is_(True), ScenarioTask.level_min <= level + 1).order_by(ScenarioTask.level_min, ScenarioTask.id)
    ).scalars().all()
    if not candidates:
        return None

    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": "You choose the next prompt-gym scenario for a management learner. Favor variety, progression, and the weakest current skill. Respond only as JSON with task_id and rationale."
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            {
                                "profile": {
                                    "xp": profile.xp,
                                    "level": level,
                                    "streak": profile.streak,
                                },
                                "recent_history": summarize_history(session, limit=8),
                                "candidates": [
                                    {
                                        "id": task.id,
                                        "title": task.title,
                                        "domain": task.domain,
                                        "skill_focus": task.skill_focus,
                                        "difficulty": task.difficulty,
                                        "learner_goal": task.learner_goal,
                                    }
                                    for task in candidates
                                ],
                            }
                        ),
                    }
                ],
            },
        ],
        "text": {"format": {"type": "json_schema", "name": "next_task", "schema": {"type": "object", "properties": {"task_id": {"type": "integer"}, "rationale": {"type": "string"}}, "required": ["task_id", "rationale"], "additionalProperties": False}}},
    }
    data = call_openai(payload)
    if not data:
        return None
    try:
        parsed = json.loads(extract_output_text(data) or "{}")
        task = session.get(ScenarioTask, int(parsed["task_id"]))
        if not task:
            return None
        return RecommendationResult(task=task, rationale=parsed["rationale"], source="llm")
    except (KeyError, ValueError, json.JSONDecodeError, TypeError):
        return None


def heuristic_coaching(task: ScenarioTask, payload: CompleteAttemptIn) -> CoachingResult:
    strengths = []
    gaps = []
    if len(payload.prompt_text) > 220:
        strengths.append("You gave the AI a meaningful amount of context.")
    else:
        gaps.append("Add more situational context so the AI can reason inside the real management situation.")
    if "\n" in payload.prompt_text or ":" in payload.prompt_text:
        strengths.append("Your prompt hints at structure instead of staying purely conversational.")
    else:
        gaps.append("Ask for a clearer output structure such as bullets, options, recommendation, and risks.")
    if payload.strategic_rating <= 3:
        gaps.append("Push harder on tradeoffs, risks, and decision relevance.")
    if payload.clarity_rating <= 3:
        gaps.append("State the audience and end-use more explicitly.")
    if payload.outcome_fit >= 4:
        strengths.append("Your self-rating suggests the prompt was already moving toward useful output.")

    summary = " ".join(strengths[:2] + gaps[:2]) or "Solid rep. Keep tightening how you frame audience, decision, and output shape."
    tweaks = "- Name the audience and decision context.\n- Add 2-3 concrete constraints.\n- Ask for options, tradeoffs, and a recommended structure."
    revised_prompt = (
        f"You are helping with a {task.domain} task. Context: {task.prompt_brief} "
        f"Goal: {task.learner_goal} Audience: specify the decision-maker or stakeholder. "
        f"Please produce: 1) key considerations, 2) 2-3 options with tradeoffs, 3) a recommendation, 4) risks or blind spots. "
        f"Tone: practical, concise, and suitable for real management use.\n\n"
        f"Draft to improve from:\n{payload.prompt_text.strip()}"
    )
    return CoachingResult(summary=summary, tweaks=tweaks, revised_prompt=revised_prompt, source="heuristic")


def llm_coaching(task: ScenarioTask, payload: CompleteAttemptIn) -> CoachingResult | None:
    schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "tweaks": {"type": "string"},
            "revised_prompt": {"type": "string"},
        },
        "required": ["summary", "tweaks", "revised_prompt"],
        "additionalProperties": False,
    }
    prompt_payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": "You are a prompt coach for strategy, leadership, and management scenarios. The learner does not share the AI output, only the original prompt and their reflection. Assess the prompt quality from what is available. Give practical coaching. Do not mention privacy unless necessary. Respond only as JSON matching the schema."
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            {
                                "scenario": {
                                    "title": task.title,
                                    "domain": task.domain,
                                    "skill_focus": task.skill_focus,
                                    "brief": task.prompt_brief,
                                    "goal": task.learner_goal,
                                    "reflection_hint": task.reflection_hint,
                                },
                                "learner_submission": payload.model_dump(),
                                "coaching_requirements": {
                                    "summary_style": "2-4 sentences, direct and practical",
                                    "tweaks_style": "3 bullet-like lines inside one string",
                                    "revised_prompt_style": "improved full prompt the learner can paste into ChatGPT or Copilot"
                                },
                            }
                        ),
                    }
                ],
            },
        ],
        "text": {"format": {"type": "json_schema", "name": "prompt_coaching", "schema": schema}},
    }
    data = call_openai(prompt_payload)
    if not data:
        return None
    try:
        parsed = json.loads(extract_output_text(data) or "{}")
        return CoachingResult(
            summary=parsed["summary"].strip(),
            tweaks=parsed["tweaks"].strip(),
            revised_prompt=parsed["revised_prompt"].strip(),
            source="llm",
        )
    except (KeyError, TypeError, json.JSONDecodeError, AttributeError):
        return None


def get_or_create_today_recommendation(session: Session, profile: LearnerProfile, force_refresh: bool = False) -> DailyRecommendation:
    day_key = current_day_key()
    if not force_refresh:
        existing = session.execute(
            select(DailyRecommendation).where(DailyRecommendation.day_key == day_key).order_by(desc(DailyRecommendation.created_at))
        ).scalars().first()
        if existing:
            return existing

    result = llm_recommendation(session, profile) or heuristic_recommendation(session, profile)
    rec = DailyRecommendation(day_key=day_key, task_id=result.task.id, rationale=result.rationale, source=result.source)
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def list_badges(session: Session) -> list[dict[str, Any]]:
    awards = session.execute(select(BadgeAward).order_by(BadgeAward.created_at)).scalars().all()
    return [{"code": a.code, "label": a.label, "description": a.description} for a in awards]


def maybe_unlock_badge(session: Session, profile: LearnerProfile, attempt: PromptAttempt, task: ScenarioTask) -> str | None:
    attempts = session.scalar(select(func.count(PromptAttempt.id))) or 0
    strategy_count = session.scalar(
        select(func.count(PromptAttempt.id)).join(ScenarioTask, PromptAttempt.task_id == ScenarioTask.id).where(ScenarioTask.domain == "strategy")
    ) or 0
    clarity_count = session.scalar(
        select(func.count(PromptAttempt.id)).join(ScenarioTask, PromptAttempt.task_id == ScenarioTask.id).where(ScenarioTask.skill_focus.in_(["clarity", "structure"]))
    ) or 0
    reflective_count = session.scalar(select(func.count(PromptAttempt.id)).where(func.length(PromptAttempt.reflection_text) >= 180)) or 0

    candidates = []
    if attempts == 1:
        candidates.append("first_rep")
    if profile.streak >= 3:
        candidates.append("three_day_streak")
    if clarity_count >= 2:
        candidates.append("clarity_builder")
    if strategy_count >= 3:
        candidates.append("strategy_lens")
    if reflective_count >= 3:
        candidates.append("reflective_operator")

    existing = {code for (code,) in session.execute(select(BadgeAward.code)).all()}
    unlocked = next((code for code in candidates if code not in existing), None)
    if not unlocked:
        return None
    badge = next(item for item in BADGES if item["code"] == unlocked)
    session.add(BadgeAward(**badge))
    attempt.badge_unlocked = badge["label"]
    return badge["label"]


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "gwen-prompt-gym", "timestamp": utc_now().isoformat()}


@app.get("/api/bootstrap")
def bootstrap() -> dict[str, Any]:
    with SessionLocal() as session:
        profile = session.get(LearnerProfile, 1)
        if not profile:
            raise HTTPException(status_code=500, detail="Learner profile missing")
        recommendation = get_or_create_today_recommendation(session, profile)
        task = session.get(ScenarioTask, recommendation.task_id)
        attempts = session.execute(
            select(PromptAttempt, ScenarioTask)
            .join(ScenarioTask, PromptAttempt.task_id == ScenarioTask.id)
            .order_by(desc(PromptAttempt.created_at))
            .limit(6)
        ).all()
        progress = progress_in_level(profile.xp)
        avg_outcome = session.scalar(select(func.avg(PromptAttempt.outcome_fit))) or 0
        avg_clarity = session.scalar(select(func.avg(PromptAttempt.clarity_rating))) or 0
        return {
            "profile": {
                "displayName": profile.display_name,
                "xp": profile.xp,
                "streak": profile.streak,
                "level": progress["level"],
                "levelProgress": progress,
            },
            "today": {
                "dayKey": recommendation.day_key,
                "task": serialize_task(task),
                "rationale": recommendation.rationale,
                "source": recommendation.source,
            },
            "history": [serialize_attempt(attempt, task_row) for attempt, task_row in attempts],
            "badges": list_badges(session),
            "stats": {
                "tasksCompleted": session.scalar(select(func.count(PromptAttempt.id))) or 0,
                "averageOutcomeFit": round(avg_outcome, 2),
                "averageClarity": round(avg_clarity, 2),
            },
        }


@app.post("/api/task/refresh")
def refresh_task(payload: RefreshTaskIn) -> dict[str, Any]:
    with SessionLocal() as session:
        profile = session.get(LearnerProfile, 1)
        if not profile:
            raise HTTPException(status_code=500, detail="Learner profile missing")
        if payload.display_name:
            profile.display_name = payload.display_name.strip() or profile.display_name
        recommendation = get_or_create_today_recommendation(session, profile, force_refresh=True)
        task = session.get(ScenarioTask, recommendation.task_id)
        session.commit()
        return {"today": {"dayKey": recommendation.day_key, "task": serialize_task(task), "rationale": recommendation.rationale, "source": recommendation.source}}


@app.post("/api/task/complete")
def complete_task(payload: CompleteAttemptIn) -> dict[str, Any]:
    with SessionLocal() as session:
        profile = session.get(LearnerProfile, 1)
        task = session.get(ScenarioTask, payload.task_id)
        if not profile or not task:
            raise HTTPException(status_code=404, detail="Task or learner profile not found")

        coaching = llm_coaching(task, payload) or heuristic_coaching(task, payload)
        xp_awarded = task.xp_reward + max(payload.outcome_fit - 3, 0) * 5 + max(payload.clarity_rating - 3, 0) * 4 + max(payload.strategic_rating - 3, 0) * 4
        attempt = PromptAttempt(
            task_id=task.id,
            prompt_text=payload.prompt_text.strip(),
            reflection_text=payload.reflection_text.strip(),
            outcome_fit=payload.outcome_fit,
            clarity_rating=payload.clarity_rating,
            structure_rating=payload.structure_rating,
            strategic_rating=payload.strategic_rating,
            confidence_after=payload.confidence_after,
            improvement_focus=payload.improvement_focus.strip().lower(),
            xp_awarded=xp_awarded,
            coach_summary=coaching.summary,
            coach_tweaks=coaching.tweaks,
            revised_prompt=coaching.revised_prompt,
        )
        session.add(attempt)

        previous_level = level_from_xp(profile.xp)
        profile.xp += xp_awarded
        today = utc_now().date()
        if profile.last_completed_on and profile.last_completed_on.date() == today:
            pass
        elif profile.last_completed_on and (today - profile.last_completed_on.date()).days == 1:
            profile.streak += 1
        else:
            profile.streak = 1
        profile.last_completed_on = utc_now()

        session.flush()
        badge_label = maybe_unlock_badge(session, profile, attempt, task)
        session.commit()
        session.refresh(profile)
        session.refresh(attempt)

        new_level = level_from_xp(profile.xp)
        recommendation = get_or_create_today_recommendation(session, profile, force_refresh=True)
        next_task = session.get(ScenarioTask, recommendation.task_id)

        return {
            "result": serialize_attempt(attempt, task),
            "profile": {
                "xp": profile.xp,
                "streak": profile.streak,
                "level": new_level,
                "levelProgress": progress_in_level(profile.xp),
                "levelUp": new_level > previous_level,
            },
            "coaching": {
                "summary": coaching.summary,
                "tweaks": coaching.tweaks,
                "revisedPrompt": coaching.revised_prompt,
                "source": coaching.source,
            },
            "badgeUnlocked": badge_label,
            "next": {
                "task": serialize_task(next_task),
                "rationale": recommendation.rationale,
                "source": recommendation.source,
            },
            "celebration": celebration_message(task.title, xp_awarded, new_level, new_level > previous_level, badge_label),
        }


@app.get("/api/tasks")
def list_tasks() -> dict[str, Any]:
    with SessionLocal() as session:
        tasks = session.execute(select(ScenarioTask).where(ScenarioTask.active.is_(True)).order_by(ScenarioTask.level_min, ScenarioTask.id)).scalars().all()
        return {"tasks": [serialize_task(task) for task in tasks]}


def celebration_message(task_title: str, xp_awarded: int, level: int, level_up: bool, badge_label: str | None) -> str:
    parts = [f"You earned {xp_awarded} XP for '{task_title}'."]
    if level_up:
        parts.append(f"Level up: you are now level {level}.")
    if badge_label:
        parts.append(f"Badge unlocked: {badge_label}.")
    return " ".join(parts)
