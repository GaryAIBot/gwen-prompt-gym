import json
import os
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Any
from urllib import request

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from psycopg.rows import dict_row


APP_TITLE = "Gwen Prompt Gym"
LEARNER_NAME = "Gwen"
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
OPENAI_RECOMMENDER_MODEL = os.getenv("OPENAI_RECOMMENDER_MODEL", "gpt-4.1-mini")

TASKS = [
    {
        "id": "clarify-goal",
        "title": "Brief Whisperer",
        "tagline": "Turn a fuzzy ask into a sharp strategic prompt.",
        "scenario": "A CEO says: 'Figure out why this quarter felt off and tell me what to do next.'",
        "instructions": "Write a prompt that gets an AI assistant to clarify the goal, surface missing context, and frame the output for an exec audience.",
        "focus": "clarity",
        "level": 1,
        "points": 70,
        "badge": "Signal Finder",
    },
    {
        "id": "exec-summary",
        "title": "Boardroom Compress",
        "tagline": "Condense noise into a crisp executive readout.",
        "scenario": "You have raw notes from five customer interviews and three internal leaders.",
        "instructions": "Create a prompt that asks the AI to produce a 5-bullet exec summary, highlight risks, and separate evidence from inference.",
        "focus": "synthesis",
        "level": 1,
        "points": 80,
        "badge": "Crisp Communicator",
    },
    {
        "id": "tradeoff-mapper",
        "title": "Tradeoff Tamer",
        "tagline": "Make the model show its work on options and consequences.",
        "scenario": "A leadership team is split between growth, margin, and product quality priorities.",
        "instructions": "Write a prompt that makes the AI compare 3 strategic options, call out tradeoffs, and recommend a decision framework rather than a shallow answer.",
        "focus": "tradeoffs",
        "level": 2,
        "points": 95,
        "badge": "Decision Cartographer",
    },
    {
        "id": "stakeholder-reframe",
        "title": "Stakeholder Shape-shift",
        "tagline": "Adapt one analysis for multiple audiences.",
        "scenario": "You need one message for the CFO, one for product leaders, and one for frontline managers.",
        "instructions": "Craft a prompt that asks the AI to rewrite the same recommendation for each audience while keeping the facts consistent.",
        "focus": "audience",
        "level": 2,
        "points": 90,
        "badge": "Audience Alchemist",
    },
    {
        "id": "scenario-planning",
        "title": "Scenario Spark",
        "tagline": "Push the AI to think in branches, not single paths.",
        "scenario": "A new competitor may enter your market in the next 6 months.",
        "instructions": "Create a prompt that generates best case, base case, and worst case scenarios with leadership actions for each.",
        "focus": "foresight",
        "level": 3,
        "points": 110,
        "badge": "Future Scout",
    },
    {
        "id": "meeting-prep",
        "title": "Meeting Boss Fight",
        "tagline": "Prompt for sharper questions before the room gets expensive.",
        "scenario": "You have a high-stakes strategy review with the executive team tomorrow morning.",
        "instructions": "Write a prompt that asks the AI to prepare the most important questions, likely objections, and a suggested meeting flow.",
        "focus": "facilitation",
        "level": 3,
        "points": 105,
        "badge": "Room Runner",
    },
]
TASK_LOOKUP = {task["id"]: task for task in TASKS}
SCHEMA_READY = False

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS learners (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    total_points INTEGER NOT NULL DEFAULT 0,
    skill_level INTEGER NOT NULL DEFAULT 1,
    streak_days INTEGER NOT NULL DEFAULT 0,
    last_completed_on TEXT,
    feedback_summary TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS task_attempts (
    id SERIAL PRIMARY KEY,
    learner_id INTEGER NOT NULL REFERENCES learners(id),
    task_id TEXT NOT NULL,
    response_text TEXT NOT NULL,
    coach_feedback TEXT NOT NULL,
    gwen_feedback TEXT NOT NULL,
    points_awarded INTEGER NOT NULL,
    completed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS badges (
    id SERIAL PRIMARY KEY,
    learner_id INTEGER NOT NULL REFERENCES learners(id),
    badge_name TEXT NOT NULL,
    awarded_at TEXT NOT NULL,
    UNIQUE (learner_id, badge_name)
);
"""


class SubmitTaskPayload(BaseModel):
    learner_name: str = Field(default=LEARNER_NAME)
    task_id: str
    response_text: str = Field(min_length=8, max_length=4000)
    gwen_feedback: str = Field(min_length=2, max_length=500)


app = FastAPI(title=APP_TITLE)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_iso() -> str:
    return date.today().isoformat()


def require_database_url() -> str:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required. This app now uses Neon Postgres only.")
    return DATABASE_URL


def ensure_schema() -> None:
    global SCHEMA_READY
    if SCHEMA_READY:
        return
    database_url = require_database_url()
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.execute(
                """
                INSERT INTO learners (name, created_at, total_points, skill_level, streak_days, feedback_summary)
                VALUES (%s, %s, 0, 1, 0, %s)
                ON CONFLICT (name) DO NOTHING
                """,
                (LEARNER_NAME, utc_now(), "Fresh start. Gwen is warming up her strategic prompting muscles."),
            )
        conn.commit()
    SCHEMA_READY = True


@contextmanager
def db_conn():
    ensure_schema()
    with psycopg.connect(require_database_url(), row_factory=dict_row) as conn:
        yield conn


def row_get(row: Any, key: str) -> Any:
    return row[key]


def get_learner(conn: Any, learner_name: str = LEARNER_NAME) -> Any:
    learner = conn.execute("SELECT * FROM learners WHERE name = %s", (learner_name,)).fetchone()
    if not learner:
        raise HTTPException(status_code=404, detail="Learner not found")
    return learner


def get_attempted_task_ids(conn: Any, learner_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT task_id FROM task_attempts WHERE learner_id = %s ORDER BY completed_at DESC",
        (learner_id,),
    ).fetchall()
    return [row_get(row, "task_id") for row in rows]


def summarize_progress(conn: Any, learner: Any) -> dict[str, Any]:
    learner_id = row_get(learner, "id")
    attempts = conn.execute(
        """
        SELECT task_id, points_awarded, coach_feedback, gwen_feedback, completed_at
        FROM task_attempts
        WHERE learner_id = %s
        ORDER BY completed_at DESC
        """,
        (learner_id,),
    ).fetchall()
    badges = conn.execute(
        "SELECT badge_name FROM badges WHERE learner_id = %s ORDER BY awarded_at",
        (learner_id,),
    ).fetchall()
    attempted_ids = [row_get(row, "task_id") for row in attempts]
    completion_ratio = round(len(attempted_ids) / len(TASKS), 2)
    return {
        "learner": row_get(learner, "name"),
        "total_points": row_get(learner, "total_points"),
        "skill_level": row_get(learner, "skill_level"),
        "streak_days": row_get(learner, "streak_days"),
        "last_completed_on": row_get(learner, "last_completed_on"),
        "feedback_summary": row_get(learner, "feedback_summary"),
        "completed_tasks": attempted_ids,
        "attempt_count": len(attempted_ids),
        "badges": [row_get(row, "badge_name") for row in badges],
        "completion_ratio": completion_ratio,
        "recent_attempts": [dict(row) for row in attempts[:4]],
    }


def heuristic_next_task(learner: Any, attempted_ids: list[str], feedback_summary: str) -> dict[str, Any]:
    remaining = [task for task in TASKS if task["id"] not in attempted_ids]
    if not remaining:
        remaining = TASKS
    target_level = max(1, min(3, row_get(learner, "skill_level")))
    feedback_text = feedback_summary.lower()
    focus_weights = {
        "clarity": 0,
        "synthesis": 0,
        "tradeoffs": 0,
        "audience": 0,
        "foresight": 0,
        "facilitation": 0,
    }
    if "clar" in feedback_text or "specific" in feedback_text:
        focus_weights["clarity"] += 2
    if "audience" in feedback_text or "stakeholder" in feedback_text:
        focus_weights["audience"] += 2
    if "option" in feedback_text or "tradeoff" in feedback_text:
        focus_weights["tradeoffs"] += 2
    ranked = sorted(
        remaining,
        key=lambda task: (
            abs(task["level"] - target_level),
            -focus_weights.get(task["focus"], 0),
            task["level"],
        ),
    )
    return ranked[0]


def recommend_next_task_with_llm(learner: Any, progress: dict[str, Any]) -> tuple[dict[str, Any], str]:
    remaining = [task for task in TASKS if task["id"] not in progress["completed_tasks"]]
    if not remaining:
        remaining = TASKS

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        fallback = heuristic_next_task(learner, progress["completed_tasks"], row_get(learner, "feedback_summary"))
        return fallback, "Heuristic pick because OPENAI_API_KEY is missing."

    payload = {
        "model": OPENAI_RECOMMENDER_MODEL,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You choose the next best micro-learning prompt task for a leadership-focused learner. "
                            "Return strict JSON with keys task_id and reason. Keep reason under 28 words."
                        ),
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
                                "learner": {
                                    "name": row_get(learner, "name"),
                                    "skill_level": row_get(learner, "skill_level"),
                                    "total_points": row_get(learner, "total_points"),
                                    "streak_days": row_get(learner, "streak_days"),
                                    "feedback_summary": row_get(learner, "feedback_summary"),
                                },
                                "recent_attempts": progress["recent_attempts"],
                                "remaining_tasks": remaining,
                            }
                        ),
                    }
                ],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "task_recommendation",
                "schema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["task_id", "reason"],
                    "additionalProperties": False,
                },
            }
        },
    }
    req = request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=25) as response:
            body = json.loads(response.read().decode("utf-8"))
        output_text = body["output"][0]["content"][0]["text"]
        parsed = json.loads(output_text)
        task = TASK_LOOKUP.get(parsed.get("task_id"))
        if task:
            return task, parsed.get("reason", "LLM-picked next challenge.")
    except Exception:
        pass

    fallback = heuristic_next_task(learner, progress["completed_tasks"], row_get(learner, "feedback_summary"))
    return fallback, "Heuristic pick because the model recommendation was unavailable."


def award_points(task: dict[str, Any], response_text: str, gwen_feedback: str) -> tuple[int, str]:
    richness = min(len(response_text) // 80, 20)
    reflection = 10 if len(gwen_feedback.strip()) >= 20 else 4
    points = task["points"] + richness + reflection
    feedback = (
        f"Strong move. You pushed on {task['focus']} and gave the model a sharper job to do. "
        "Next time, tighten the output format and success criteria even more."
    )
    return points, feedback


def calculate_streak(last_completed_on: str | None, today: str, current_streak: int) -> int:
    if not last_completed_on:
        return 1
    last_date = date.fromisoformat(str(last_completed_on))
    today_date = date.fromisoformat(today)
    delta_days = (today_date - last_date).days
    if delta_days == 0:
        return current_streak
    if delta_days == 1:
        return current_streak + 1
    return 1


@app.exception_handler(Exception)
async def handle_exception(_request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/api/profile-state")
def profile_state():
    with db_conn() as conn:
        learner = get_learner(conn)
        progress = summarize_progress(conn, learner)
        next_task, reason = recommend_next_task_with_llm(learner, progress)
        return {
            "app_title": APP_TITLE,
            "storage_mode": "neon-postgres",
            "profile": progress,
            "levels": {
                "current": row_get(learner, "skill_level"),
                "next_level_points": row_get(learner, "skill_level") * 240,
            },
            "next_task": {**next_task, "recommendation_reason": reason},
        }


@app.get("/api/next-task")
def next_task():
    with db_conn() as conn:
        learner = get_learner(conn)
        progress = summarize_progress(conn, learner)
        task, reason = recommend_next_task_with_llm(learner, progress)
        return {"task": task, "reason": reason}


@app.get("/api/progress-summary")
def progress_summary():
    with db_conn() as conn:
        learner = get_learner(conn)
        progress = summarize_progress(conn, learner)
        meter = min(100, int((progress["total_points"] / 720) * 100))
        return {
            "summary": progress,
            "progress_meter": meter,
            "remaining_tasks": [task for task in TASKS if task["id"] not in progress["completed_tasks"]],
        }


@app.post("/api/submit-task")
def submit_task(payload: SubmitTaskPayload):
    task = TASK_LOOKUP.get(payload.task_id)
    if not task:
        raise HTTPException(status_code=400, detail="Unknown task")

    with db_conn() as conn:
        learner = get_learner(conn, payload.learner_name)
        learner_id = row_get(learner, "id")
        points, coach_feedback = award_points(task, payload.response_text, payload.gwen_feedback)
        completed_at = utc_now()

        conn.execute(
            """
            INSERT INTO task_attempts (
                learner_id, task_id, response_text, coach_feedback, gwen_feedback, points_awarded, completed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                learner_id,
                task["id"],
                payload.response_text.strip(),
                coach_feedback,
                payload.gwen_feedback.strip(),
                points,
                completed_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO badges (learner_id, badge_name, awarded_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (learner_id, badge_name) DO NOTHING
            """,
            (learner_id, task["badge"], completed_at),
        )

        today = today_iso()
        streak_days = calculate_streak(row_get(learner, "last_completed_on"), today, row_get(learner, "streak_days"))
        total_points = row_get(learner, "total_points") + points
        skill_level = max(1, min(3, 1 + total_points // 240))
        completion_count = len(get_attempted_task_ids(conn, learner_id))
        feedback_summary = (
            f"Latest reflection: {payload.gwen_feedback.strip()} | "
            f"Recent strength: {task['focus']} | Total completions: {completion_count}"
        )

        conn.execute(
            """
            UPDATE learners
            SET total_points = %s, skill_level = %s, streak_days = %s, last_completed_on = %s, feedback_summary = %s
            WHERE id = %s
            """,
            (total_points, skill_level, streak_days, today, feedback_summary, learner_id),
        )
        conn.commit()

    with db_conn() as read_conn:
        learner = get_learner(read_conn, payload.learner_name)
        progress = summarize_progress(read_conn, learner)
        next_task_data, reason = recommend_next_task_with_llm(learner, progress)
        return {
            "result": {
                "points_awarded": points,
                "coach_feedback": coach_feedback,
                "badge_unlocked": task["badge"],
            },
            "profile": progress,
            "next_task": {**next_task_data, "recommendation_reason": reason},
        }


@app.get("/api/health")
def health():
    try:
        ensure_schema()
        with db_conn() as conn:
            table_rows = conn.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('learners', 'task_attempts', 'badges')
                ORDER BY table_name
                """
            ).fetchall()
        return {
            "ok": True,
            "app": APP_TITLE,
            "db_backend": "postgres",
            "database_url_present": bool(DATABASE_URL),
            "tables": [row_get(row, "table_name") for row in table_rows],
        }
    except Exception as exc:
        return {
            "ok": False,
            "app": APP_TITLE,
            "db_backend": "postgres",
            "database_url_present": bool(DATABASE_URL),
            "error": str(exc),
        }
