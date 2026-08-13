# Tredro Backend

B2B SaaS API backend. This repository contains the Django REST API that the
frontend (separate Vercel repo) will consume.

## Technology stack

- Python 3.13
- Django + Django REST Framework
- PostgreSQL
- Redis + Celery
- Docker / Docker Compose
- GitHub Codespaces / Dev Containers
- Gunicorn (production)

## Repository structure

```text
.
├── .devcontainer/          # Codespaces / VS Code Dev Container
├── .github/workflows/      # CI
├── apps/                   # Django applications
│   └── health/             # Health-check endpoint only (for now)
├── config/                 # Django project package
│   ├── settings/           # base / development / production
│   └── celery.py
├── docker/                 # Container entry helpers
├── tests/                  # Pytest suite
├── Dockerfile              # Production-oriented image (Gunicorn)
├── docker-compose.yml      # Local / Codespaces development
├── docker-compose.prod.yml # Single-VPS production starting point
├── manage.py
├── requirements.txt
└── .env.example
```

Structural note: a small `apps/health` app hosts `GET /api/health/` so the
`config` package stays limited to project wiring. No business/domain apps yet.

## Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin)
- Git
- Optional locally: Python 3.13 for running tooling outside containers

## Environment variable setup

```bash
cp .env.example .env
```

Edit `.env` as needed. Never commit `.env`.

Key variables:

| Variable | Purpose |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.development` or `config.settings.production` |
| `DJANGO_SECRET_KEY` | Django secret key |
| `DJANGO_DEBUG` | `True` / `False` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts |
| `DATABASE_*` | PostgreSQL connection |
| `REDIS_URL` | Redis connection |
| `CELERY_BROKER_URL` | Celery broker (usually same Redis) |

## Run with Docker Compose (recommended)

```bash
cp .env.example .env
docker compose up --build
```

Services:

- `backend` — Django (`http://localhost:8000`)
- `postgres` — PostgreSQL
- `redis` — Redis
- `celery` — Celery worker
- `celery-beat` — Celery beat scheduler

Stop:

```bash
docker compose down
```

## Migrations

Compose starts the backend with non-destructive migrations. To run manually:

```bash
docker compose exec backend python manage.py migrate
```

## Create a superuser

```bash
docker compose exec backend python manage.py createsuperuser
```

## Run tests

```bash
docker compose exec backend pytest
```

## Health endpoint

```bash
curl http://localhost:8000/api/health/
```

Expected response:

```json
{"status":"ok"}
```

## GitHub Codespaces

1. Open the repository in a Codespace (or VS Code Dev Containers: "Reopen in Container").
2. The Dev Container uses this repo's `docker-compose.yml` (Postgres/Redis via Compose, not duplicated inside the Codespace).
3. Ensure `.env` exists (`cp .env.example .env` if needed).
4. After the environment is up, hit the forwarded port `8000` at `/api/health/`.

## Local development notes

Preferred path is Docker Compose so Postgres/Redis/Celery match production topology.

If you install Python deps on the host for editors/tooling:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Point `DATABASE_HOST` / `REDIS_URL` at Compose-published ports (`localhost`) when running management commands on the host.

## Production deployment concept (single Linux VPS)

1. Copy the project to the VPS.
2. Create a production `.env` with strong secrets (`DJANGO_DEBUG=False`, real `DJANGO_SECRET_KEY`, locked-down `DJANGO_ALLOWED_HOSTS`).
3. Start:

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

4. Put Nginx or Caddy in front of `localhost:8000` for TLS and static/media later.
5. Postgres and Redis stay on the internal Docker network (not published publicly).
6. SSL/Cloudflare are intentionally out of scope for this foundation.

## Useful commands

```bash
# Django system checks
docker compose exec backend python manage.py check

# Shell
docker compose exec backend python manage.py shell

# Follow logs
docker compose logs -f backend
```
