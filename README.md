# Gwen Prompt Gym

Tiny FastAPI + static frontend micro-learning app for Gwen to practice AI prompting for leadership and strategy work.

## Local run

1. Set `OPENAI_API_KEY`.
2. Optionally set `BLOB_READ_WRITE_TOKEN` if you want durable Blob-backed SQLite locally too.
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

2. Create a private Blob store and capture the token:

```bash
vercel blob create-store gwen-prompt-gym --access private
```

3. Add env vars to the Vercel project:

```bash
vercel env add OPENAI_API_KEY production
vercel env add OPENAI_API_KEY preview
vercel env add BLOB_READ_WRITE_TOKEN production
vercel env add BLOB_READ_WRITE_TOKEN preview
```

4. Deploy:

```bash
vercel --prod
```

## Notes

- Durable progress is stored in SQLite, then snapshotted to a private Vercel Blob after each write.
- If the LLM recommender is unavailable, the app falls back to a deterministic heuristic task picker.
