# CI/CD Pipeline

## Tiering strategy

pytest markers (`smoke`, `regression`, `performance`) partition all 53 tests, matching the spec's stated purpose per tier:

| Tier | Files | Trigger | Dataset |
|---|---|---|---|
| **Smoke** | infrastructure sanity, constraint validation, ACID rollback, API-to-DB consistency, duplicate transaction prevention, money conservation | Every push/PR | `small` (100 customers) |
| **Regression** | referential integrity, audit log validation, balance reconciliation, concurrency | Nightly + manual | `medium` (10,000 customers) |
| **Performance** | query plan validation | Manual only | `large` (100,000 customers) |

Regression runs `smoke or regression` (a superset), not just its own tier — standard practice so a regression run also re-confirms the fast checks still hold at a larger scale.

## Workflows

**`smoke.yml`** — two parallel jobs, so the Docker build never bottlenecks the fast test feedback loop:
- `test`: Ruff lint + Ruff format check → run migrations → seed small → run smoke-marked tests with `pytest-xdist` (`-n auto --dist loadfile`) and coverage → upload to Codecov
- `docker`: build the image with Buildx (GitHub Actions cache backend) → scan with Trivy (reports CRITICAL/HIGH findings, doesn't currently fail the build)

**`regression.yml`** — nightly cron + manual dispatch, seeds `medium`, runs `smoke or regression`.

**`performance.yml`** — manual dispatch only, seeds `large`, runs the performance suite, generates the informational `EXPLAIN ANALYZE` report, and uploads it as a build artifact.

## Docker layer caching

```dockerfile
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev
```

Dependencies are installed in their own layer, before the rest of the code is copied in — so a code-only change doesn't invalidate the (slower) dependency-install layer, only the final sync.

## Dependabot

Configured across all three ecosystems present in this repo: `pip` (reads `pyproject.toml`), `github-actions`, and `docker` — weekly checks on each.

## A real lesson learned: two formatters drifting apart

Pre-commit has enforced `ruff format` on every commit since Phase 1 — but CI was originally checking with `black --check .` instead. Individually reasonable tools, but different enough that small differences accumulated across several commits before CI caught it. The fix wasn't reformatting once (that just drifts again on the next commit) — it was making CI check the *same* tool pre-commit actually enforces:

```yaml
- name: Ruff format check
  run: uv run ruff format --check .
```

Black remains installed as an optional manual dev tool, just no longer part of the automated enforcement chain.
