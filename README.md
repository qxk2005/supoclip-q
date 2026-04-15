# Fuck OpusClip.

... because good video clips shouldn't cost a fortune or come with ugly watermarks.

<p align="center">
  <a href="https://www.supoclip.com">
    <img src="assets/banner.png" alt="SupoClip Banner" width="100%" />
  </a>
</p>

OpusClip charges $15–29/month and slaps watermarks on every free video. SupoClip gives you AI-powered clipping—open source, watermark-free when you self-host, with an optional hosted offering.

> Hosted version waitlist: [SupoClip Hosted](https://www.supoclip.com)

## Why SupoClip Exists

### The OpusClip Problem

OpusClip is undeniably powerful (long-form → shorts, captions, virality scoring, templates). **The catch:** tight free quotas, watermarks on free exports, paid minute caps, and platform lock-in.

### The SupoClip Solution

- **Self-hosted control** — your data, your hardware limits.
- **No OpusClip-style watermarks** on your own deployment.
- ** AGPL-3.0** — inspect and extend the code.
- **Hosted product** — when `SELF_HOST=false`, Stripe-backed plans and limits apply (see monetization env vars in `.env.example`).

## What the repo actually does today

Monorepo: **Next.js 15** (App Router) frontend, **FastAPI** backend (`src/main_refactored.py`), **ARQ** worker + **Redis** queue, **PostgreSQL** for tasks/clips/auth.

| Layer | Reality |
|--------|--------|
| **Transcription** | **faster-whisper** (local CPU), word-level timings cached next to the video as `.transcript_cache.json`. Processing mode picks model size (`FAST_MODE_TRANSCRIPT_MODEL`, etc.). |
| **Clip selection** | **pydantic-ai** + your configured `LLM` (Google / OpenAI / Anthropic / Ollama) analyzes the timestamped transcript. |
| **Rendering** | **MoviePy** — vertical 9:16 (optional original aspect), face-aware crop, caption templates, optional B-roll (Pexels). |
| **Bilingual captions** | Task flag `bilingual_subtitles_mode`: `auto` uses **English-only** detection to add **CN primary + EN secondary** (EN two font sizes smaller than your chosen size). Uses the same LLM for phrase translation. See `backend/migrations/006_add_bilingual_subtitles.sql` and API field `bilingual_subtitles_mode`. |
| **Legacy entrypoint** | `src/main.py` still references AssemblyAI in places; **day-to-day development uses `main_refactored` + the worker**, not that path. |

## Quick Start

### Prerequisites

- **PostgreSQL 15+**, **Redis**, **ffmpeg** on `PATH`
- **Python 3.11+** with [**uv**](https://github.com/astral-sh/uv)
- **Node.js** (LTS) for the frontend
- **One LLM provider key** (or Ollama) matching `LLM=provider:model` — required for analysis (and bilingual translation when enabled)
- Optional: **Pexels** (`PEXELS_API_KEY`), **Apify** (`APIFY_API_TOKEN`) for YouTube download path, **Resend** / **Stripe** when running hosted billing

### 1. Clone and configure

```bash
git clone <your-fork-or-upstream-url>
cd supoclip
cp .env.example .env
# Edit .env: DATABASE_URL, Redis, LLM + matching API keys, etc.
```

`.env.example` still lists `ASSEMBLY_AI_API_KEY` for historical/legacy flows; **the refactored worker pipeline does not require it** for transcription. If you use tooling that expects it, you can leave it blank for local whisper-only runs.

Minimal variables to process a video locally:

```env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/supoclip
# Frontend Prisma often uses postgresql:// (sync driver) — see .env.example

REDIS_HOST=localhost
REDIS_PORT=6379

LLM=google-gla:gemini-3-flash-preview
GOOGLE_API_KEY=your_key

BETTER_AUTH_SECRET=change_me
```

Tune whisper / clip caps (optional):

```env
DEFAULT_PROCESSING_MODE=fast
FAST_MODE_MAX_CLIPS=4
FAST_MODE_TRANSCRIPT_MODEL=tiny
BALANCED_MODE_TRANSCRIPT_MODEL=medium
QUALITY_MODE_TRANSCRIPT_MODEL=large-v3
```

### 2. Database schema

```bash
# Core schema (repo root)
psql "$DATABASE_URL" -f init.sql

# Backend incremental columns (always apply if your DB is older than the repo)
for f in backend/migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done

# Frontend (Better Auth + Task tables Prisma manages)
cd frontend && npx prisma migrate deploy
```

Use a `postgresql+asyncpg://` URL for the **Python** backend; the **frontend** `DATABASE_URL` is often a `postgresql://` URL for Prisma (configure in the env files you use for `npm run dev` / `next build`).

### 3. Run the stack (three terminals)

```bash
./start.sh   # checklist; follow the printed commands
```

Typical processes:

1. **API** — `cd backend && uv sync && source .venv/bin/activate && uvicorn src.main_refactored:app --reload --host 0.0.0.0 --port 8000`
2. **Worker** (required) — `cd backend && source .venv/bin/activate && arq src.workers.tasks.WorkerSettings`
3. **Frontend** — `cd frontend && npm install && npm run dev`

- App: http://localhost:3000  
- API docs: http://localhost:8000/docs  

### 4. Troubleshooting (condensed)

| Symptom | Check |
|--------|--------|
| API key errors on start | `LLM` prefix must match a configured key (`GOOGLE_API_KEY`, `OPENAI_API_KEY`, …) or use `LLM=ollama:...` with Ollama running. |
| Tasks stuck **queued** | Worker running? Redis reachable? |
| Prisma / DB errors | Migrations applied; URLs match driver (asyncpg vs prisma). |
| Empty font list | Fonts under `backend/fonts/` — [backend/fonts/README.md](backend/fonts/README.md). |

More detail: [docs/troubleshooting.md](docs/troubleshooting.md), [CLAUDE.md](CLAUDE.md), [AGENTS.md](AGENTS.md).

## Testing

The repo **does** ship automated tests; depth varies by area.

| Command | What it runs |
|---------|----------------|
| `make test` | Backend pytest + frontend Vitest with coverage (see Makefile env vars). |
| `make test-backend` | `cd backend && uv sync --all-groups && pytest` — **note:** `pyproject.toml` enforces `--cov-fail-under=65` on a **subset** of modules (`auth_headers`, `billing_service`). |
| `make test-frontend` | Vitest with coverage. |
| `make test-e2e` | Playwright (runs `prisma migrate deploy` first). |

For quick backend iteration on other packages:

```bash
cd backend && uv run pytest tests/unit/ -q --no-cov
```

Full-stack local tests expect Postgres and Redis (Makefile defaults to `127.0.0.1` URLs—adjust `DATABASE_URL` / `TEST_DATABASE_URL` as needed).

## Documentation

Extended docs live under [`docs/`](docs/README.md):

- [docs/setup.md](docs/setup.md) · [docs/configuration.md](docs/configuration.md) · [docs/app-guide.md](docs/app-guide.md)  
- [docs/architecture.md](docs/architecture.md) · [docs/api-reference.md](docs/api-reference.md) · [docs/development.md](docs/development.md) · [docs/troubleshooting.md](docs/troubleshooting.md)

## Hosted billing (optional)

When monetization is enabled (`SELF_HOST=false`), Stripe + Resend flows apply—see README section in-repo near env vars `STRIPE_*`, `RESEND_*`, `BACKEND_AUTH_SECRET`, and the docs above.

## License

SupoClip is released under the **AGPL-3.0** License. See [LICENSE](LICENSE).
