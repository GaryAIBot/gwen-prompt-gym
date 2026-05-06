# Gwen Prompt Gym

Tiny FastAPI + static frontend micro-learning app for Gwen to practice AI prompting for leadership and strategy work.

## Storage model

This app now uses **Neon Postgres only**.

Required environment variables:

- `DATABASE_URL`
- `OPENAI_API_KEY`

On first request, the backend automatically creates these tables if they do not already exist:

- `gwen_prompt_gym_learners`
- `gwen_prompt_gym_task_attempts`
- `gwen_prompt_gym_badges`

## Local run

1. Set `DATABASE_URL`.
2. Set `OPENAI_API_KEY`.
3. Run:

```bash
vercel dev
```

Then open `http://localhost:3000`.

## Deploy

1. Link or create the Vercel project:

```bash
vercel link
```

2. Add env vars to the Vercel project:

```bash
vercel env add DATABASE_URL production
vercel env add OPENAI_API_KEY production
```

3. Deploy:

```bash
vercel --prod
```

## Notes

- The app creates and seeds the database automatically.
- `/api/health` reports whether the Neon connection is present and which required tables it can see.
- If the LLM recommender is unavailable, the app falls back to a deterministic heuristic task picker.
