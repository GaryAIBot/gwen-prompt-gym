import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib import error, request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, desc, func, inspect, select
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
    output_score: Mapped[int] = mapped_column(Integer, default=0)
    prompt_score: Mapped[int] = mapped_column(Integer, default=0)
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
    {"code": "first_rep", "label": "First Rep", "description": "Completed the first workout."},
    {"code": "three_reps", "label": "Combo Starter", "description": "Completed three prompt reps."},
    {"code": "five_reps", "label": "Gym Regular", "description": "Completed five prompt reps."},
    {"code": "three_day_streak", "label": "Three-Day Streak", "description": "Completed prompt workouts on three consecutive days."},
    {"code": "five_day_streak", "label": "Five-Day Fire", "description": "Reached a five-day streak."},
    {"code": "clarity_builder", "label": "Clarity Builder", "description": "Completed two reps focused on clarity or structure."},
    {"code": "strategy_lens", "label": "Strategy Lens", "description": "Completed three strategy-domain scenarios."},
    {"code": "leadership_pulse", "label": "Leadership Pulse", "description": "Completed two leadership-domain scenarios."},
    {"code": "workday_alchemist", "label": "Workday Alchemist", "description": "Turned a real work prompt into a gym rep."},
    {"code": "reflective_operator", "label": "Reflective Operator", "description": "Wrote three strong reflections."},
    {"code": "high_score", "label": "Boss Fight Clear", "description": "Completed a rep with strong self-ratings across the board."},
]


class CompleteAttemptIn(BaseModel):
    task_id: int
    prompt_text: str = Field(min_length=8, max_length=5000)
    reflection_text: str = Field(min_length=8, max_length=2500)
    outcome_fit: int = Field(ge=1, le=5)
    clarity_rating: int = Field(ge=1, le=5)
    structure_rating: int = Field(ge=1, le=5)
    strategic_rating: int = Field(ge=1, le=5)
    confidence_after: int = Field(ge=1, le=5)
    improvement_focus: str = Field(min_length=3, max_length=80)
    feedback_mode: str = Field(default="quick_coach", pattern="^(quick_coach|sharp_reviewer|strategic_mentor)$")


class RefreshTaskIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)


class CreatePromptQuestIn(BaseModel):
    prompt_text: str = Field(min_length=8, max_length=5000)


class RecoachIn(BaseModel):
    task_id: int
    prompt_text: str = Field(min_length=8, max_length=5000)
    reflection_text: str = Field(min_length=8, max_length=2500)
    outcome_fit: int = Field(ge=1, le=5)
    clarity_rating: int = Field(ge=1, le=5)
    structure_rating: int = Field(ge=1, le=5)
    strategic_rating: int = Field(ge=1, le=5)
    confidence_after: int = Field(ge=1, le=5)
    improvement_focus: str = Field(min_length=3, max_length=80)
    feedback_mode: str = Field(default="quick_coach", pattern="^(quick_coach|sharp_reviewer|strategic_mentor)$")


@dataclass
class RecommendationResult:
    task: ScenarioTask
    rationale: str
    source: str


@dataclass
class CoachingResult:
    verdict: str
    strongest: str
    missing: str
    why_matters: str
    revised_prompt: str
    prompt_score: int
    output_score: int
    source: str
    mode: str


@dataclass
class GeneratedTask:
    title: str
    domain: str
    skill_focus: str
    difficulty: int
    xp_reward: int
    prompt_brief: str
    learner_goal: str
    reflection_hint: str
    rationale: str
    source: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def current_day_key() -> str:
    return utc_now().date().isoformat()


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned[:48] or "quest"


def level_from_xp(xp: int) -> int:
    return max(1, (xp // LEVEL_SIZE) + 1)


def progress_in_level(xp: int) -> dict[str, int]:
    level = level_from_xp(xp)
    base = (level - 1) * LEVEL_SIZE
    return {"level": level, "current": xp - base, "needed": LEVEL_SIZE}


def rank_title(level: int) -> str:
    titles = {
        1: "Prompt Rookie",
        2: "Clarity Operator",
        3: "Strategy Crafter",
        4: "Leadership Tactician",
        5: "Prompt Captain",
        6: "Executive Whisperer",
    }
    return titles.get(level, "Prompt Sensei")


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_prompt_attempt_columns()
    seed_data()


def ensure_prompt_attempt_columns() -> None:
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("prompt_attempts")}
    statements = []
    if "output_score" not in columns:
        statements.append("ALTER TABLE prompt_attempts ADD COLUMN output_score INTEGER DEFAULT 0")
    if "prompt_score" not in columns:
        statements.append("ALTER TABLE prompt_attempts ADD COLUMN prompt_score INTEGER DEFAULT 0")
    if not statements:
        return
    with engine.begin() as conn:
        for stmt in statements:
            conn.exec_driver_sql(stmt)


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
        "isCustom": task.slug.startswith("work-") or task.slug.startswith("live-") or task.slug.startswith("custom-"),
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
        "outputScore": attempt.output_score,
        "promptScore": attempt.prompt_score,
        "coachSummary": attempt.coach_summary,
        "coachTweaks": attempt.coach_tweaks,
        "revisedPrompt": attempt.revised_prompt,
        "badgeUnlocked": attempt.badge_unlocked,
        "createdAt": attempt.created_at.isoformat(),
        "isCustom": task.slug.startswith("work-") or task.slug.startswith("live-") or task.slug.startswith("custom-"),
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
                "output_score": attempt.output_score,
                "prompt_score": attempt.prompt_score,
                "improvement_focus": attempt.improvement_focus,
                "reflection_text": attempt.reflection_text,
                "is_custom": task.slug.startswith("work-") or task.slug.startswith("live-") or task.slug.startswith("custom-"),
            }
        )
    return history


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
        with request.urlopen(req, timeout=30) as resp:
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


def calculate_output_score(payload: CompleteAttemptIn | RecoachIn) -> int:
    ratings = [
        payload.clarity_rating,
        payload.structure_rating,
        payload.outcome_fit,
        payload.strategic_rating,
        payload.confidence_after,
    ]
    return round((sum(ratings) / len(ratings)) * 20)


def reflection_prompt_proxy_score(payload: CompleteAttemptIn | RecoachIn) -> int:
    weighted = (
        payload.outcome_fit * 1.1
        + payload.clarity_rating * 1.0
        + payload.structure_rating * 1.0
        + payload.strategic_rating * 1.2
        + payload.confidence_after * 1.1
    ) / 5.4
    return round(weighted * 20)


def output_score_from_attempt(attempt: PromptAttempt) -> int:
    if attempt.output_score:
        return attempt.output_score
    ratings = [attempt.clarity_rating, attempt.structure_rating, attempt.outcome_fit, attempt.strategic_rating, attempt.confidence_after]
    return round((sum(ratings) / len(ratings)) * 20)


def prompt_score_from_attempt(attempt: PromptAttempt) -> int:
    if attempt.prompt_score:
        return attempt.prompt_score
    proxy = (
        attempt.outcome_fit * 1.1
        + attempt.clarity_rating * 1.0
        + attempt.structure_rating * 1.0
        + attempt.strategic_rating * 1.2
        + attempt.confidence_after * 1.1
    ) / 5.4
    return round(proxy * 20)


def progress_stats(session: Session) -> dict[str, Any]:
    attempts = session.execute(select(PromptAttempt).order_by(desc(PromptAttempt.created_at))).scalars().all()
    if not attempts:
        return {
            "tasksCompleted": 0,
            "averageOutputScore": 0,
            "averagePromptScore": 0,
            "averageClarity": 0,
            "averageStrategicDepth": 0,
        }
    completed = len(attempts)
    avg_output = round(sum(output_score_from_attempt(a) for a in attempts) / completed, 1)
    avg_prompt = round(sum(prompt_score_from_attempt(a) for a in attempts) / completed, 1)
    avg_clarity = round(sum(a.clarity_rating for a in attempts) / completed, 2)
    avg_strategic = round(sum(a.strategic_rating for a in attempts) / completed, 2)
    return {
        "tasksCompleted": completed,
        "averageOutputScore": avg_output,
        "averagePromptScore": avg_prompt,
        "averageClarity": avg_clarity,
        "averageStrategicDepth": avg_strategic,
    }


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
        value += 12 if task.level_min == level else 0
        value += weak_domains.get(task.domain, 0) * 8
        value += focus_counts.get(task.skill_focus, 0) * 5
        value -= 18 if task.title in recent_titles else 0
        value += task.difficulty * 2
        return value

    best = max(tasks, key=score)
    rationale = f"Picked to match level {level} while targeting domains and prompt skills that still look uneven in your recent reps."
    return RecommendationResult(task=best, rationale=rationale, source="heuristic")


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
                                "profile": {"xp": profile.xp, "level": level, "streak": profile.streak},
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


def heuristic_prompt_quest(prompt_text: str, level: int) -> GeneratedTask:
    lower = prompt_text.lower()
    if any(word in lower for word in ["stakeholder", "board", "risk", "initiative", "strategy"]):
        domain = "strategy"
        skill_focus = "context depth"
    elif any(word in lower for word in ["feedback", "team", "colleague", "manager", "delegate"]):
        domain = "leadership"
        skill_focus = "audience awareness"
    else:
        domain = "management"
        skill_focus = "structure"

    difficulty = min(4, max(1, level))
    short = prompt_text.strip().replace("\n", " ")[:90]
    title = f"Sharpen a real work prompt: {short}" if len(short) < 60 else f"Sharpen a real work prompt: {short[:56]}…"
    return GeneratedTask(
        title=title,
        domain=domain,
        skill_focus=skill_focus,
        difficulty=difficulty,
        xp_reward=42 + min(level, 4) * 2,
        prompt_brief="This quest was created from a real prompt taken from your daily work. The goal is to make it more useful, more deliberate, and better matched to its decision context.",
        learner_goal="Use your real work prompt as the raw material. Improve the framing so the next run gets stronger judgment, clearer structure, and better practical usefulness.",
        reflection_hint="You do not need to explain the scenario separately. Judge the prompt itself: did it frame audience, objective, constraints, tradeoffs, and output shape well enough?",
        rationale="Built from your own work so the rep is immediately relevant instead of abstract.",
        source="heuristic",
    )


def llm_prompt_quest(prompt_text: str, level: int, history: list[dict[str, Any]]) -> GeneratedTask | None:
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "domain": {"type": "string"},
            "skill_focus": {"type": "string"},
            "difficulty": {"type": "integer"},
            "xp_reward": {"type": "integer"},
            "prompt_brief": {"type": "string"},
            "learner_goal": {"type": "string"},
            "reflection_hint": {"type": "string"},
            "rationale": {"type": "string"},
        },
        "required": ["title", "domain", "skill_focus", "difficulty", "xp_reward", "prompt_brief", "learner_goal", "reflection_hint", "rationale"],
        "additionalProperties": False,
    }
    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Turn a real work prompt into a motivating prompt-gym quest. The learner will not describe the scenario separately. Infer enough from the prompt alone. Keep it practical, game-like, and privacy-safe. Respond only as JSON matching the schema."
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps({"level": level, "recent_history": history[:5], "prompt_text": prompt_text}),
                    }
                ],
            },
        ],
        "text": {"format": {"type": "json_schema", "name": "generated_prompt_quest", "schema": schema}},
    }
    data = call_openai(payload)
    if not data:
        return None
    try:
        parsed = json.loads(extract_output_text(data) or "{}")
        return GeneratedTask(
            title=parsed["title"].strip()[:120],
            domain=(parsed["domain"] or "management").strip().lower()[:40],
            skill_focus=parsed["skill_focus"].strip()[:60],
            difficulty=max(1, min(5, int(parsed["difficulty"]))),
            xp_reward=max(35, min(70, int(parsed["xp_reward"]))),
            prompt_brief=parsed["prompt_brief"].strip(),
            learner_goal=parsed["learner_goal"].strip(),
            reflection_hint=parsed["reflection_hint"].strip(),
            rationale=parsed["rationale"].strip(),
            source="llm",
        )
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None


def create_prompt_quest(session: Session, profile: LearnerProfile, prompt_text: str) -> RecommendationResult:
    level = level_from_xp(profile.xp)
    history = summarize_history(session, limit=8)
    generated = llm_prompt_quest(prompt_text, level, history) or heuristic_prompt_quest(prompt_text, level)
    slug = f"work-{utc_now().strftime('%Y%m%d%H%M%S')}-{slugify(generated.title)[:24]}"
    task = ScenarioTask(
        slug=slug,
        title=generated.title,
        domain=generated.domain,
        skill_focus=generated.skill_focus,
        level_min=max(1, level),
        difficulty=generated.difficulty,
        xp_reward=generated.xp_reward,
        prompt_brief=generated.prompt_brief,
        learner_goal=generated.learner_goal,
        reflection_hint=generated.reflection_hint,
        active=False,
    )
    session.add(task)
    session.flush()

    day_key = current_day_key()
    for rec in session.execute(select(DailyRecommendation).where(DailyRecommendation.day_key == day_key)).scalars().all():
        session.delete(rec)
    recommendation = DailyRecommendation(day_key=day_key, task_id=task.id, rationale=generated.rationale, source=generated.source)
    session.add(recommendation)
    session.commit()
    session.refresh(task)
    return RecommendationResult(task=task, rationale=generated.rationale, source=generated.source)


def heuristic_coaching(task: ScenarioTask, payload: CompleteAttemptIn) -> CoachingResult:
    mode = payload.feedback_mode
    output_score = calculate_output_score(payload)
    prompt_score = reflection_prompt_proxy_score(payload)
    strengths = []
    gaps = []
    if payload.clarity_rating >= 4:
        strengths.append("The result sounds understandable enough to use without heavy decoding.")
    if payload.structure_rating >= 4:
        strengths.append("The result seems organized enough to reuse quickly.")
    if payload.outcome_fit >= 4:
        strengths.append("The answer appears reasonably on-target for the real task.")
    if payload.strategic_rating >= 4:
        strengths.append("The answer seems to carry some real judgment rather than empty polish.")
    if payload.confidence_after >= 4:
        strengths.append("The output looks usable enough to move the work forward.")

    if payload.clarity_rating <= 3:
        gaps.append("The answer likely still lacks crispness and may be making you work too hard to understand it.")
    if payload.structure_rating <= 3:
        gaps.append("The answer likely needs a clearer shape so the reader can scan and act faster.")
    if payload.outcome_fit <= 3:
        gaps.append("The result may still be too generic or only partially aimed at the real task.")
    if payload.strategic_rating <= 3:
        gaps.append("It probably does not surface enough tradeoffs, risks, or decision logic.")
    if payload.confidence_after <= 3:
        gaps.append("It may still need too much rewriting before it becomes useful in real work.")

    verdict_map = {
        "quick_coach": "Promising rep, but the result still needs a sharper frame to become reliably useful.",
        "sharp_reviewer": "The result is not tight enough yet; it still sounds more serviceable than strong.",
        "strategic_mentor": "The result may read well enough, but it still needs more decision value to earn trust in leadership work.",
    }
    strongest = strengths[0] if strengths else "You at least generated something concrete enough to evaluate instead of guessing in the abstract."
    missing_map = {
        "quick_coach": " ".join(gaps[:2]) or "The main gap is turning a decent answer into one that is sharper and more directly usable.",
        "sharp_reviewer": " ".join(gaps[:2]) or "The answer still lacks edge; it should be more specific, better structured, and less generic.",
        "strategic_mentor": " ".join(gaps[:2]) or "What is still missing is stronger judgment: clearer implications, better prioritization, and more obvious decision support.",
    }
    why_map = {
        "quick_coach": "If the answer is unclear, loosely structured, or generic, you lose time rewriting it and get less value from the AI run.",
        "sharp_reviewer": "Weak output creates fake progress: it looks helpful, but you still have to do the hard thinking and cleanup yourself.",
        "strategic_mentor": "In management work, a decent-sounding answer is not enough; if it does not clarify tradeoffs and implications, it does not really improve judgment.",
    }
    revised_prompt = (
        f"You are helping with a {task.domain} task. Context: {task.prompt_brief} "
        f"Goal: {task.learner_goal} Audience: specify the decision-maker or stakeholder. "
        f"Please produce: 1) a crisp answer, 2) a clear structure with headings or bullets, 3) the most relevant points only, 4) tradeoffs, risks, or implications, 5) practical next steps. "
        f"Tone: practical, concise, and suitable for real management use.\n\n"
        f"Draft to improve from:\n{payload.prompt_text.strip()}"
    )
    return CoachingResult(
        verdict=verdict_map[mode],
        strongest=strongest,
        missing=missing_map[mode],
        why_matters=why_map[mode],
        revised_prompt=revised_prompt,
        prompt_score=prompt_score,
        output_score=output_score,
        source="heuristic",
        mode=mode,
    )


def llm_coaching(task: ScenarioTask, payload: CompleteAttemptIn) -> CoachingResult | None:
    schema = {
        "type": "object",
        "properties": {
            "verdict": {"type": "string"},
            "strongest": {"type": "string"},
            "missing": {"type": "string"},
            "why_matters": {"type": "string"},
            "revised_prompt": {"type": "string"},
            "prompt_score": {"type": "integer"},
        },
        "required": ["verdict", "strongest", "missing", "why_matters", "revised_prompt", "prompt_score"],
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
                        "text": "You are a prompt coach for strategy, leadership, and management scenarios. The learner does not share the AI output, only the original prompt plus their ratings and reflection of the output. Assess the likely prompt quality from that evidence. Respond only as JSON matching the schema."
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
                                "feedback_mode": payload.feedback_mode,
                                "coaching_requirements": {
                                    "required_structure": ["verdict", "strongest", "missing", "why_matters", "best_rewrite"],
                                    "mode_definitions": {
                                        "quick_coach": "fast, short feedback",
                                        "sharp_reviewer": "direct critique, more demanding",
                                        "strategic_mentor": "focuses on judgment, tradeoffs, stakeholder thinking"
                                    },
                                    "verdict_style": "one-line judgment",
                                    "strongest_style": "name one thing working",
                                    "missing_style": "name one or two sharp gaps",
                                    "why_matters_style": "explain the consequence for output quality or decision quality",
                                    "revised_prompt_style": "improved full prompt the learner can paste into ChatGPT or Copilot",
                                    "prompt_score_style": "integer 0-100 assessing prompt quality from the available evidence"
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
            verdict=parsed["verdict"].strip(),
            strongest=parsed["strongest"].strip(),
            missing=parsed["missing"].strip(),
            why_matters=parsed["why_matters"].strip(),
            revised_prompt=parsed["revised_prompt"].strip(),
            prompt_score=round((reflection_prompt_proxy_score(payload) * 0.45) + (max(0, min(100, int(parsed["prompt_score"]))) * 0.55)),
            output_score=calculate_output_score(payload),
            source="llm",
            mode=payload.feedback_mode,
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
    for rec in session.execute(select(DailyRecommendation).where(DailyRecommendation.day_key == day_key)).scalars().all():
        session.delete(rec)
    rec = DailyRecommendation(day_key=day_key, task_id=result.task.id, rationale=result.rationale, source=result.source)
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def list_badges(session: Session) -> list[dict[str, Any]]:
    awards = session.execute(select(BadgeAward).order_by(BadgeAward.created_at)).scalars().all()
    return [{"code": a.code, "label": a.label, "description": a.description} for a in awards]


def next_badge_hint(session: Session, profile: LearnerProfile) -> dict[str, str]:
    attempts = session.scalar(select(func.count(PromptAttempt.id))) or 0
    strategy_count = session.scalar(select(func.count(PromptAttempt.id)).join(ScenarioTask, PromptAttempt.task_id == ScenarioTask.id).where(ScenarioTask.domain == "strategy")) or 0
    leadership_count = session.scalar(select(func.count(PromptAttempt.id)).join(ScenarioTask, PromptAttempt.task_id == ScenarioTask.id).where(ScenarioTask.domain == "leadership")) or 0
    clarity_count = session.scalar(select(func.count(PromptAttempt.id)).join(ScenarioTask, PromptAttempt.task_id == ScenarioTask.id).where(ScenarioTask.skill_focus.in_(["clarity", "structure"]))) or 0
    reflective_count = session.scalar(select(func.count(PromptAttempt.id)).where(func.length(PromptAttempt.reflection_text) >= 180)) or 0
    custom_count = session.scalar(select(func.count(PromptAttempt.id)).join(ScenarioTask, PromptAttempt.task_id == ScenarioTask.id).where(ScenarioTask.slug.like("work-%"))) or 0
    existing = {code for (code,) in session.execute(select(BadgeAward.code)).all()}

    checks = [
        ("first_rep", attempts, 1),
        ("three_reps", attempts, 3),
        ("five_reps", attempts, 5),
        ("three_day_streak", profile.streak, 3),
        ("five_day_streak", profile.streak, 5),
        ("clarity_builder", clarity_count, 2),
        ("strategy_lens", strategy_count, 3),
        ("leadership_pulse", leadership_count, 2),
        ("workday_alchemist", custom_count, 1),
        ("reflective_operator", reflective_count, 3),
    ]
    for code, current, needed in checks:
        if code in existing:
            continue
        label = next(item["label"] for item in BADGES if item["code"] == code)
        return {"label": label, "progress": f"{current}/{needed}"}
    return {"label": "All current badges cleared", "progress": "100%"}


def maybe_unlock_badge(session: Session, profile: LearnerProfile, attempt: PromptAttempt, task: ScenarioTask) -> str | None:
    attempts = session.scalar(select(func.count(PromptAttempt.id))) or 0
    strategy_count = session.scalar(select(func.count(PromptAttempt.id)).join(ScenarioTask, PromptAttempt.task_id == ScenarioTask.id).where(ScenarioTask.domain == "strategy")) or 0
    leadership_count = session.scalar(select(func.count(PromptAttempt.id)).join(ScenarioTask, PromptAttempt.task_id == ScenarioTask.id).where(ScenarioTask.domain == "leadership")) or 0
    clarity_count = session.scalar(select(func.count(PromptAttempt.id)).join(ScenarioTask, PromptAttempt.task_id == ScenarioTask.id).where(ScenarioTask.skill_focus.in_(["clarity", "structure"]))) or 0
    reflective_count = session.scalar(select(func.count(PromptAttempt.id)).where(func.length(PromptAttempt.reflection_text) >= 180)) or 0
    custom_count = session.scalar(select(func.count(PromptAttempt.id)).join(ScenarioTask, PromptAttempt.task_id == ScenarioTask.id).where(ScenarioTask.slug.like("work-%"))) or 0

    candidates = []
    if attempts == 1:
        candidates.append("first_rep")
    if attempts == 3:
        candidates.append("three_reps")
    if attempts == 5:
        candidates.append("five_reps")
    if profile.streak >= 3:
        candidates.append("three_day_streak")
    if profile.streak >= 5:
        candidates.append("five_day_streak")
    if clarity_count >= 2:
        candidates.append("clarity_builder")
    if strategy_count >= 3:
        candidates.append("strategy_lens")
    if leadership_count >= 2:
        candidates.append("leadership_pulse")
    if custom_count >= 1:
        candidates.append("workday_alchemist")
    if reflective_count >= 3:
        candidates.append("reflective_operator")
    if attempt.outcome_fit >= 4 and attempt.clarity_rating >= 4 and attempt.structure_rating >= 4 and attempt.strategic_rating >= 4:
        candidates.append("high_score")

    existing = {code for (code,) in session.execute(select(BadgeAward.code)).all()}
    unlocked = next((code for code in candidates if code not in existing), None)
    if not unlocked:
        return None
    badge = next(item for item in BADGES if item["code"] == unlocked)
    session.add(BadgeAward(**badge))
    attempt.badge_unlocked = badge["label"]
    return badge["label"]


def calculate_xp(task: ScenarioTask, payload: CompleteAttemptIn, profile: LearnerProfile) -> tuple[int, list[str]]:
    xp = task.xp_reward
    bonuses = []
    if payload.outcome_fit >= 4:
        xp += 6
        bonuses.append("strong outcome")
    if payload.clarity_rating >= 4:
        xp += 5
        bonuses.append("clarity boost")
    if payload.structure_rating >= 4:
        xp += 5
        bonuses.append("structure boost")
    if payload.strategic_rating >= 4:
        xp += 6
        bonuses.append("strategy boost")
    if len(payload.reflection_text.strip()) >= 180:
        xp += 8
        bonuses.append("deep reflection")
    if profile.streak >= 1:
        streak_bonus = min(profile.streak, 5) * 2
        xp += streak_bonus
        bonuses.append(f"streak +{streak_bonus}")
    if task.slug.startswith("work-"):
        xp += 8
        bonuses.append("real work quest")
    if payload.outcome_fit >= 4 and payload.clarity_rating >= 4 and payload.structure_rating >= 4 and payload.strategic_rating >= 4:
        xp += 10
        bonuses.append("perfect combo")
    return xp, bonuses


def celebration_message(task_title: str, xp_awarded: int, level: int, level_up: bool, badge_label: str | None, bonuses: list[str]) -> str:
    parts = [f"Quest cleared: '{task_title}' for {xp_awarded} XP."]
    if bonuses:
        parts.append("Bonuses: " + ", ".join(bonuses[:4]) + ".")
    if level_up:
        parts.append(f"Level up — you are now {rank_title(level)}.")
    if badge_label:
        parts.append(f"Badge unlocked: {badge_label}.")
    return " ".join(parts)


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
        stats = progress_stats(session)
        custom_count = session.scalar(select(func.count(PromptAttempt.id)).join(ScenarioTask, PromptAttempt.task_id == ScenarioTask.id).where(ScenarioTask.slug.like("work-%"))) or 0
        badges = list_badges(session)
        return {
            "profile": {
                "displayName": profile.display_name,
                "xp": profile.xp,
                "streak": profile.streak,
                "level": progress["level"],
                "levelProgress": progress,
                "rankTitle": rank_title(progress["level"]),
            },
            "today": {
                "dayKey": recommendation.day_key,
                "task": serialize_task(task),
                "rationale": recommendation.rationale,
                "source": recommendation.source,
            },
            "history": [serialize_attempt(attempt, task_row) for attempt, task_row in attempts],
            "badges": badges,
            "nextBadge": next_badge_hint(session, profile),
            "stats": {
                **stats,
                "customPromptReps": custom_count,
                "comboMeter": min(100, (stats["tasksCompleted"] * 18) + (profile.streak * 6)),
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


@app.post("/api/task/from-prompt")
def create_task_from_prompt(payload: CreatePromptQuestIn) -> dict[str, Any]:
    with SessionLocal() as session:
        profile = session.get(LearnerProfile, 1)
        if not profile:
            raise HTTPException(status_code=500, detail="Learner profile missing")
        recommendation = create_prompt_quest(session, profile, payload.prompt_text.strip())
        return {
            "today": {
                "dayKey": current_day_key(),
                "task": serialize_task(recommendation.task),
                "rationale": recommendation.rationale,
                "source": recommendation.source,
            },
            "prefillPrompt": payload.prompt_text.strip(),
            "message": "Real work prompt converted into a live quest.",
        }


@app.post("/api/task/recoach")
def recoach_task(payload: RecoachIn) -> dict[str, Any]:
    with SessionLocal() as session:
        task = session.get(ScenarioTask, payload.task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        coaching = llm_coaching(task, payload) or heuristic_coaching(task, payload)
        return {
            "coaching": {
                "verdict": coaching.verdict,
                "strongest": coaching.strongest,
                "missing": coaching.missing,
                "whyMatters": coaching.why_matters,
                "revisedPrompt": coaching.revised_prompt,
                "promptScore": coaching.prompt_score,
                "outputScore": coaching.output_score,
                "source": coaching.source,
                "mode": coaching.mode,
            }
        }


@app.post("/api/task/complete")
def complete_task(payload: CompleteAttemptIn) -> dict[str, Any]:
    with SessionLocal() as session:
        profile = session.get(LearnerProfile, 1)
        task = session.get(ScenarioTask, payload.task_id)
        if not profile or not task:
            raise HTTPException(status_code=404, detail="Task or learner profile not found")

        coaching = llm_coaching(task, payload) or heuristic_coaching(task, payload)
        xp_awarded, bonuses = calculate_xp(task, payload, profile)
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
            output_score=coaching.output_score,
            prompt_score=coaching.prompt_score,
            coach_summary=coaching.verdict,
            coach_tweaks="\n\n".join([coaching.strongest, coaching.missing, coaching.why_matters]),
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
                "rankTitle": rank_title(new_level),
            },
            "coaching": {
                "verdict": coaching.verdict,
                "strongest": coaching.strongest,
                "missing": coaching.missing,
                "whyMatters": coaching.why_matters,
                "revisedPrompt": coaching.revised_prompt,
                "promptScore": coaching.prompt_score,
                "outputScore": coaching.output_score,
                "source": coaching.source,
                "mode": coaching.mode,
            },
            "badgeUnlocked": badge_label,
            "xpBreakdown": bonuses,
            "next": {
                "task": serialize_task(next_task),
                "rationale": recommendation.rationale,
                "source": recommendation.source,
            },
            "celebration": celebration_message(task.title, xp_awarded, new_level, new_level > previous_level, badge_label, bonuses),
            "message": "Rep logged. You can now try another coach mode or move on to the next quest.",
        }


@app.get("/api/tasks")
def list_tasks() -> dict[str, Any]:
    with SessionLocal() as session:
        tasks = session.execute(select(ScenarioTask).where(ScenarioTask.active.is_(True)).order_by(ScenarioTask.level_min, ScenarioTask.id)).scalars().all()
        return {"tasks": [serialize_task(task) for task in tasks]}
