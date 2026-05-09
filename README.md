# Gwen Prompt Gym

Tiny app for deliberate prompt practice in strategy, leadership, and management contexts.

## Current product shape

- stronger gamification: rank titles, combo meter, streak energy, XP bonuses, and broader badge unlocks
- two quest entry modes:
  - **gym scenario** from the curated task pool
  - **real work prompt** generated from a prompt pasted from daily work
- privacy-safe workflow: learner shares only the prompt used plus reflection and self-ratings
- AI coaching now returns a structured review:
  - verdict
  - what’s strongest
  - what’s missing
  - why that matters
  - best rewrite
- learner can choose among 3 feedback modes:
  - **Quick coach**
  - **Sharp reviewer**
  - **Strategic mentor**
- the app now shows both:
  - an **output score** from the learner reflection ratings
  - a **prompt score** blended from learner reflection signals plus LLM prompt assessment
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

## Next iteration notes

### Feedback redesign ideas

Current concern: feedback still feels too generic and coach-y. It comments on the prompt, but does not yet deliver enough high-value judgment.

Possible feedback models to explore next:

1. **Diagnostic feedback**
   - main weakness
   - why that weakness matters
   - best next edit

2. **Before/after rewrite feedback**
   - original prompt
   - improved prompt
   - 3 annotated changes

3. **Prompt scorecard**
   - clarity
   - context
   - audience framing
   - constraints
   - output format
   - strategic depth
   - tradeoff awareness
   - plus: strongest element, weakest element, highest-leverage fix

4. **Managerial judgment feedback**
   - not only whether the prompt is well written
   - also whether it drives useful decision support, tradeoffs, stakeholder sensitivity, and strategic thinking

5. **Reflection-quality feedback**
   - separate feedback on prompt quality vs reflection quality
   - reward good self-diagnosis even when the prompt itself is mediocre

6. **Challenge-back feedback**
   - more opinionated pushback, e.g.:
   - you asked for help but not alternatives
   - you framed output but not the decision
   - this prompt optimizes for text production, not decision support

### Recommended future feedback structure

Best candidate structure:

1. verdict
2. what is strongest
3. what is missing
4. why that matters
5. best next rewrite
6. what to test next

### Possible feedback modes

- **Quick coach** — short and fast
- **Sharp reviewer** — more direct critique
- **Strategic mentor** — focuses on judgment, tradeoffs, stakeholder thinking

### Product direction reminder

The distinctive move is to shift from pure prompt-writing feedback toward **decision-quality feedback** for leadership, strategy, and management work.

## Notes

- The app does **not** require the learner to upload the AI output.
- The learner does **not** need to describe the scenario separately when using a real work prompt.
- Table names are un-namespaced because the intended production setup is one Neon project per app.
