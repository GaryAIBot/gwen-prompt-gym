# Gwen Prompt Gym

Tiny app MVP for deliberate prompt practice in strategy, leadership, and management contexts.

## Core workflow

1. learner gets a scenario
2. learner tests a prompt in an external AI tool
3. learner returns only with:
   - the prompt they used
   - structured self-ratings
   - free-text reflection
4. app assesses prompt craft and reflection quality
5. app returns coaching feedback, suggested tweaks, and a revised prompt
6. learner gains XP, levels, badges, and an adapted next scenario

## Stack

- static `index.html`
- FastAPI backend in `api/index.py`
- Postgres via `DATABASE_URL` (Neon for production)
- Vercel hosting via explicit `vercel.json`
- optional OpenAI coaching and task adaptation when `OPENAI_API_KEY` is set

## Local run

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn api.index:app --reload
```

Open `http://127.0.0.1:8000/api/health` for backend health and serve `index.html` with any static server if needed.

## Environment variables

- `DATABASE_URL` - Postgres connection string; defaults to local SQLite for dev
- `OPENAI_API_KEY` - enables LLM coaching and next-task recommendation
- `OPENAI_MODEL` - optional, defaults to `gpt-4.1-mini`

## Notes

- The app does **not** require the learner to upload the AI output.
- Table names are un-namespaced because the intended production setup is one Neon project per app.
