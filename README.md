# Overwatch

A conversational AI that captures the commitments you make to yourself in natural language and surgically reminds you of them — so your plans don't die from neglect.

## Status

🚧 Personal-use MVP in active development: Android app + FastAPI backend.

## The problem

You write a to-do list in the morning. By 11am, you stop looking at it. By evening, you've forgotten half of it.

The problem isn't *planning* — it's *re-engagement*. Plans don't die from being unmade. They die from being forgotten.

## What this is

A system that captures commitments you make in everyday conversation ("I'll start prep at 2:30", "10 applications this week") and follows up at exactly the times you said. Not a calendar. Not a to-do app. A memory layer over your stated commitments.

See [`docs/PRD.md`](docs/PRD.md) for the full product vision.

## Tech stack

- **Backend:** Python 3.12, FastAPI
- **Mobile app:** React Native + Expo (Android) — the only client
- **Database:** SQLite (Railway volume in production, local file in dev)
- **LLM:** OpenAI → Groq → Ollama fallback chain

## Getting started

See [`docs/HANDBOOK.md`](docs/HANDBOOK.md) §6 for full setup. Short version:

```bash
# Backend (Python 3.12)
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]" && cp .env.example .env   # fill in keys
uvicorn app.main:app --reload --port 8000

# Mobile
cd mobile && npm ci
npx expo run:android
```

## Documentation

**Start here:** [`docs/HANDBOOK.md`](docs/HANDBOOK.md) — bird's-eye view, reading order, request walkthrough.

- [`docs/HANDBOOK.md`](docs/HANDBOOK.md) — One-page project map (read this first)
- [`docs/PRD.md`](docs/PRD.md) — Product Requirements Document
- [`docs/EDD.md`](docs/EDD.md) — Engineering Design Document
- [`docs/adr/`](docs/adr/) — Architectural Decision Records
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — How to work in this repo

## License

TBD
