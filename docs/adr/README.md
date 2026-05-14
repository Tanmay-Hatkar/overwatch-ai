# Architectural Decision Records (ADRs)

This folder contains the history of significant architectural decisions made on this project. Each decision gets its own numbered file, written *when the decision is made*, and **never edited after the fact**.

## Why we keep ADRs

Code shows *what*. Git history shows *what changed*. Neither shows *why* the decision was made.

ADRs answer that.

Three months from now, you'll forget why you chose Postgres over MongoDB, why you put commitments and todos in separate tables, why you decided against multi-tenancy. ADRs preserve that reasoning.

ADRs are also a strong signal in interviews / code reviews — they show that decisions were *considered*, not accidental.

## Format

Each ADR is a single markdown file named `NNNN-short-description.md`, where `NNNN` is a zero-padded sequential number.

See [`template.md`](template.md) for the structure.

## Status values

- **Proposed** — under discussion, not yet decided
- **Accepted** — decision made, in effect
- **Deprecated** — no longer recommended; may still be in code
- **Superseded by NNNN** — explicitly replaced by a newer ADR (link to it)

## Rules

1. **Number sequentially.** The next ADR is one more than the highest existing number.
2. **Never edit a historical ADR.** If a decision changes, write a *new* ADR that supersedes the old one. The old one stays in the repo unchanged. ADRs are a historical record, not a wiki.
3. **Be specific.** Bad: "Use a good database." Good: "Use Postgres because we need JSON column support and we're already on Supabase."
4. **Include consequences.** What does this decision enable? What does it lock us out of?
5. **Link to references.** Discussions, PRs, external docs that informed the decision.
