# Copilot Instructions

## Mandatory project rules

- This repo is PRI MVP.
- Follow Block 0 before any other feature work: PostgreSQL 15 + pgvector + SQLModel, no Redis.
- If the user explicitly asks to switch the AI provider, prefer Gemini instead of ChatGPT/OpenAI for that change.
- Do not add nationality to candidate data or scoring flow. `CandidateProfile` must not carry `nationality` for scoring use.
- Keep `evaluation` and `decision` append-only forever. Never `UPDATE` or `DELETE` historical rows.
- `application.status` must be derived from the latest decision, not manually overwritten.
- `user.email` must remain unique.
- Keep vector similarity indexes on `candidateprofile` and `joboffer` with `vector_cosine_ops`.
- Do not introduce unsupported database patterns or extra infrastructure.
- Prefer SQLModel models consistent with the existing schema style in [backend/app/models/__init__.py](../backend/app/models/__init__.py).
- If a task touches the database, verify it does not violate Block 0 rules and append-only history requirements before finishing.

## Never do

- Do not reintroduce nationality-based scoring or prompt injection of nationality.
- Do not allow updates to `evaluation` or `decision` rows.
- Do not add Redis or unrelated cache services.
- Do not ignore PostgreSQL 15 + pgvector requirements.
