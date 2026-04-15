# Setup

This guide covers local development: PostgreSQL, Redis, backend API, ARQ worker, and frontend.

## Requirements

### Required software

- Git  
- Python 3.11+ and [uv](https://github.com/astral-sh/uv)  
- Node.js compatible with Next.js 15  
- PostgreSQL 15+  
- Redis  
- FFmpeg on your PATH (for the backend / worker)  

### Required credentials

- `ASSEMBLY_AI_API_KEY`  
- One LLM provider configuration (see `.env.example`)  

### Optional credentials

- `PEXELS_API_KEY` for AI B-roll  
- DataFast, Resend, Stripe, Discord webhooks as described in [Configuration](./configuration.md)  

## First-time setup

### 1. Clone and env

```bash
git clone <your-repo-url>
cd supoclip
cp .env.example .env
```

Edit `.env`: set API keys, `DATABASE_URL` (Postgres), and `REDIS_HOST` / `REDIS_PORT` (and password if used).

### 2. Database schema

From the repo root:

```bash
psql "$DATABASE_URL" -f init.sql
```

If you are upgrading an older database, also run the SQL files in `backend/migrations/` in order.

### 3. Run services

```bash
./start.sh
```

The script prints commands for three processes. In separate terminals:

**Backend**

```bash
cd backend
uv venv .venv && source .venv/bin/activate
uv sync
uvicorn src.main_refactored:app --reload --host 0.0.0.0 --port 8000
```

**Worker** (required for video jobs)

```bash
cd backend
source .venv/bin/activate
arq src.workers.tasks.WorkerSettings
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

### 4. Open the app

- Frontend: `http://localhost:3000`  
- API docs: `http://localhost:8000/docs`  

## First-run checklist

1. Load the homepage.  
2. Create an account or sign in.  
3. Submit a YouTube URL or upload a video.  
4. Confirm the task progresses and clips appear when the worker is running.  

## Data layout

- Uploads and generated clips default under `TEMP_DIR` (see `backend/src/config.py`).  
- Custom fonts: `backend/fonts/`  
- Transitions: `backend/transitions/`  

## Hosted vs self-hosted

See [Configuration](./configuration.md) for `SELF_HOST`, Stripe, and auth secrets.

## Next steps

- [Configuration](./configuration.md)  
- [App guide](./app-guide.md)  
- [Troubleshooting](./troubleshooting.md)  
