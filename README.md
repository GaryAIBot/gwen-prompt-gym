# Gwen Prompt Gym

Tiny app for deliberate prompt practice in strategy, leadership, and management contexts.

## Current product shape

- stronger gamification: rank titles, combo meter, streak energy, XP bonuses, and broader badge unlocks
- two quest entry modes:
  - **gym scenario** from the curated task pool
  - **real work prompt** generated from a prompt pasted from daily work
- privacy-safe workflow: learner shares only the prompt used plus reflection and self-ratings
- AI coaching returns assessment, suggested tweaks, and a revised prompt draft
- adaptive next-task selection based on history and current level
- explicit loading states so the app signals when it is generating or loading a quest

## Stack

- static `index.html`
- FastAPI backend in `api/index.py`
- Postgres via `DATABASE_URL` (Neon for production)
- Vercel hosting via explicit `vercel.json`
- optional OpenAI coaching, task adaptation, and real-work quest generation when `OPENAI_API_KEY` is set

## Local run

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn api.index:app --reload
```

## Notes

- The app does **not** require the learner to upload the AI output.
- The learner does **not** need to describe the scenario separately when using a real work prompt.
- Table names are un-namespaced because the intended production setup is one Neon project per app.
