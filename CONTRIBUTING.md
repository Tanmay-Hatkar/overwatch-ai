# Contributing to Overwatch

This document defines how work happens in this repo: branching, commits, PRs, and conventions. Even for solo development, following these makes the project legible and portfolio-grade.

---

## Branch strategy

**Trunk-based development.**

- `main` is always deployable. Tests pass on every commit to `main`.
- All work happens on **short-lived feature branches** (ideally 1–3 days).
- **Never push directly to `main`.** Always PR — *even when working solo*. Forces self-review.
- **Never force-push to `main`.**

### Branch naming

Format: `<type>/<short-description>` (kebab-case)

| Type | Examples |
|---|---|
| `feat/` | `feat/todo-crud`, `feat/llm-fallback` |
| `fix/` | `fix/timezone-events`, `fix/silent-todo-create` |
| `refactor/` | `refactor/repository-pattern` |
| `docs/` | `docs/add-adr-0003` |
| `chore/` | `chore/upgrade-fastapi` |
| `test/` | `test/cover-edge-cases-todo` |

---

## Commit messages — Conventional Commits

Format: `<type>(<scope>): <subject>`

Examples:

```
feat(todos): add priority field to Todo model
fix(calendar): correct timezone offset for week query
refactor(llm): extract provider classes from orchestrator
chore(deps): upgrade pydantic to 2.6
test(repo): cover empty-state path in TodoRepository.list()
docs(adr): record decision to use Supabase as production DB
```

### Rules

- **Subject:** imperative mood ("add", not "added"), lowercase, no period, ≤72 chars
- **Body (optional):** explain *why*, not *what*. Code shows what. Body shows reasoning.
- **Footer (optional):** `Closes #12`, `Refs #34`, `BREAKING CHANGE: ...`

### Types

| Type | Use for |
|---|---|
| `feat:` | new feature |
| `fix:` | bug fix |
| `refactor:` | no behavior change, internal cleanup |
| `test:` | test additions/changes only |
| `docs:` | documentation only |
| `chore:` | build, deps, tooling |
| `style:` | formatting/whitespace only |
| `perf:` | performance improvement |

---

## Pull requests

- **Title** = future commit message (Conventional Commit format) — because we squash-merge
- **Description template:**

```markdown
## What
- bullet list of what changed

## Why
the motivation, the problem this solves

## How to test
steps to verify, or "tests cover this"

## Linked issues
Closes #X
```

- **Self-review** before requesting merge. Read your own diff. Catch your own typos.
- **CI green** required before merge.
- **One PR = one logical change.** Don't bundle a refactor with a feature with a bug fix. Separate them.

---

## Merge strategy: squash merge

- Every PR becomes one clean commit on `main`
- Keeps `git log main` readable as a feature-by-feature history
- Branch's internal history (50 "wip" commits) gets discarded — you don't need it after merge

---

## Tagging releases — Semantic Versioning

- `v0.1.0` — first MVP slice complete
- `v0.1.1` — bug fix
- `v0.2.0` — significant new features
- `v1.0.0` — when YOU consider it production-ready

After merging the relevant PR:

```bash
git tag v0.1.0
git push origin v0.1.0
```

---

## Pre-commit hooks (added in slice 1)

Every commit will auto-run:

- **ruff** — Python lint (fails on style/quality issues)
- **ruff format** — Python formatter (auto-fixes formatting)
- **mypy** — type checker
- **pytest** (fast subset) — unit tests
- **prettier** — frontend formatter

If any fail, the commit is blocked.

**Rule:** never use `git commit --no-verify` to skip hooks. If a hook fails, fix the underlying issue.

---

## Anti-patterns — do not do these

- ❌ `git commit -am "fixed stuff"` — meaningless, useless in `git log`
- ❌ Pushing directly to `main` — bypasses self-review and CI
- ❌ Force-pushing to `main` — destroys history
- ❌ `git commit --no-verify` — bypasses safety hooks
- ❌ Rebasing a branch others have already pulled — rewrites their history
- ❌ Committing secrets (API keys, OAuth tokens) — even if you delete the file later, it stays in git history forever
- ❌ Committing `node_modules/`, `__pycache__/`, `.env`, build artifacts — handle via `.gitignore`
- ❌ Giant PRs touching 30+ unrelated files — break them up
