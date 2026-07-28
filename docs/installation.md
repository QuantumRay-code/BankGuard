#Installation Guide

## Prerequisites

| Tool | Notes |
|---|---|
| Git | any recent version |
| [uv](https://docs.astral.sh/uv/) | manages the Python version and dependencies — no separate Python install needed |
| Docker Desktop | runs PostgreSQL 17; on Windows, uses the WSL 2 backend |

## Setup

```bash
git clone https://github.com/QuantumRay-code/BankGuard.git
cd BankGuard
uv sync
```

Copy `.env.example` to `.env` (the values already match `docker-compose.yml`, no editing needed):
```bash
cp .env.example .env      # macOS/Linux
copy .env.example .env    # Windows
```

Start PostgreSQL:
```bash
docker compose up -d
docker compose ps   # confirm "healthy"
```

Run migrations, then seed a dataset:
```bash
uv run python scripts/run_migrations.py
uv run python script/seed_data.py --profile small
```

Three profiles are available - 'small' (100 customers, fast local iteration), 'medium'  (10,000, the primary dataset for functional/regression testing), `large` (100,000, for performance validation). Re-running `seed_data.py` refuses to run against an already-seeded database; reset first with `docker compose down -v && docker compose up -d` before switching profiles.

Start the API:
```bash
uv run uvicorn main:app --reload
```
Interactive docs at 'http://localhost:8000/docs'.

In second terminal, run the test:
```bash
uv run pytest -m smoke -v
```

## Troubleshooting

**Docker Desktop: "Virtualization support not detected" (Windows)** — this means WSL 2 isn't fully set up, not a hardware problem in most cases. In an admin PowerShell:
```powershell
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```
Restart, then:
```powershell
wsl --update
wsl --set-default-version 2
```
Restart Docker Desktop.

**Migration runner fails with a connection error** — confirm `docker compose ps` shows the container as `healthy` before running migrations; the healthcheck exists specifically so other tooling can wait for genuine readiness rather than just "container started."
