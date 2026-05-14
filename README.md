# Overwatch

A conversational AI that captures the commitments you make to yourself in natural language and surgically reminds you of them — so your plans don't die from neglect.

## Status

🚧 Early development. Building toward a personal-use MVP.

## The problem

You write a to-do list in the morning. By 11am, you stop looking at it. By evening, you've forgotten half of it.

The problem isn't *planning* — it's *re-engagement*. Plans don't die from being unmade. They die from being forgotten.

## What this is

A system that captures commitments you make in everyday conversation ("I'll start prep at 2:30", "10 applications this week") and follows up at exactly the times you said. Not a calendar. Not a to-do app. A memory layer over your stated commitments.

See [`docs/PRD.md`](docs/PRD.md) for the full product vision.

## Tech stack

- **Backend:** Python 3.12, FastAPI
- **Frontend:** React + Vite
- **Database:** Postgres (Supabase) + SQLite (local dev)
- **LLM:** OpenAI → Groq → Ollama fallback chain
- **Calendar integration:** Google Calendar API

## Getting started

_Setup instructions will be added once slice 1 is complete._

## Documentation

- [`docs/PRD.md`](docs/PRD.md) — Product Requirements Document
- [`docs/EDD.md`](docs/EDD.md) — Engineering Design Document
- [`docs/adr/`](docs/adr/) — Architectural Decision Records
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — How to work in this repo

## License

TBD
