# 0001: Vertical slicing and OOP-where-helpful as core development methodology

- **Status:** Accepted
- **Date:** 2026-05-06
- **Deciders:** Tanmay Hatkar

## Context

Overwatch v1 (at `c:\Tanmay\Self-Study\overwatch-ai-productivity-planner`) was built **horizontally** — all backend first, then all frontend, then all integrations. The result was a half-working app where every feature was 60% complete, nothing was actually usable, no version control, no CI, no portfolio-grade artifact.

For v2, we needed a methodology that:

- Produces shippable progress at every step
- Allows learning to happen alongside building
- Looks professional in a portfolio / interview review
- Avoids the v1 trap of accumulating half-finished surface area

We also had to decide on a code style: pure procedural Python (idiomatic, simple), OOP-everywhere (Java-style, visibly architectural), or a hybrid.

## Decision

**Methodology: Vertical slicing.**

Each slice builds one feature end-to-end through every layer (Model → Repository → Service → Route → UI → Tests → CI → merged PR) **before** the next slice begins. A slice is "done" only when fully shipped and merged to `main` with green CI.

**Code style: OOP where it helps, functions where it doesn't.**

- Classes for: stateful logic (Repositories, Services), polymorphism (LLM providers, calendar providers), domain entities.
- Functions for: pure utilities (date formatters), FastAPI route handlers, Pydantic models (already classes — no methods needed).
- **SOLID principles applied universally** regardless of class vs function.

## Alternatives considered

- **Horizontal layering** — build all data models first, then all repositories, then all services, etc.
  Rejected because: v1 already failed this way. No usable artifact until weeks in. No learning feedback loop. Fragile to scope changes.

- **Refactor v1 in place** — rewrite incrementally instead of starting fresh.
  Rejected because: v1's architectural drift (procedural throughout) is harder to retrofit than to rewrite. Refactoring while bug-fixing is two changes at once — hard to know what broke what.

- **Pure procedural Python** — functions everywhere, no classes except Pydantic models.
  Rejected because: idiomatic for small projects, but classes provide visible architecture for portfolio review. Repository and Service patterns are easier to demonstrate in interviews than free-floating functions.

- **OOP everywhere (Java-style)** — every module is a class, including pure utilities.
  Rejected because: unidiomatic in Python, fights FastAPI conventions (routes are functions), adds ceremony without benefit.

## Consequences

### Positive

- Every slice produces a shippable artifact — progress visible from week 1.
- Learning happens in context — theory paired with applied work sticks better than pure reading.
- Clean OOP architecture visible to reviewers (`TodoRepository`, `TodoService`, etc.) — interview-ready.
- Per-slice merges create natural ADR moments — each significant decision gets recorded.
- Rollback is cheap — a bad slice = revert one PR.

### Negative

- Some "infrastructure" work (e.g., logging conventions, test fixtures) gets defined later than it would in a top-down design — added during the slice that first needs it.
- Cross-slice abstractions (e.g., a base `Repository` class) emerge *after* slice 1, not before — accepted as the price of avoiding speculative design.
- More upfront process per slice (PR, self-review, CI, ADR) — slower for the first few slices, faster after the rhythm sets in.

## References

- Discussion that led to this decision: chat history dated 2026-04-30 → 2026-05-06 ("methodology reset" conversation).
- v1 codebase as the negative example: `c:\Tanmay\Self-Study\overwatch-ai-productivity-planner`.
