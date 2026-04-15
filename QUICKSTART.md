# SupoClip Quick Start (local)

## Prerequisites

1. **PostgreSQL 15+** and **Redis** running and reachable from your machine  
2. **Python 3.11+**, **Node 20+**, **ffmpeg** on your PATH  
3. **API keys** (see `.env.example`):
   - [AssemblyAI](https://www.assemblyai.com/) for transcription  
   - One hosted LLM key (OpenAI / Google / Anthropic) or [Ollama](https://ollama.com/) locally  

## Steps

```bash
git clone https://github.com/FujiwaraChoki/supoclip.git
cd supoclip
cp .env.example .env
# Edit .env: ASSEMBLY_AI_API_KEY, LLM + provider key, DATABASE_URL, REDIS_*

psql "$DATABASE_URL" -f init.sql
# Apply backend/migrations/*.sql if upgrading an older database

./start.sh
```

Follow the printed checklist: run **backend** (`uvicorn`), **worker** (`arq`), and **frontend** (`npm run dev`) in separate terminals.

- App: http://localhost:3000  
- API: http://localhost:8000/docs  

## Tests

With Postgres and Redis available (same host/ports as in `DATABASE_URL` / `REDIS_*`):

```bash
cd backend && uv sync --all-groups && .venv/bin/pytest
cd frontend && npm install && npm run test:coverage
```

## Troubleshooting

- **Queued tasks**: ensure `arq src.workers.tasks.WorkerSettings` is running from `backend/`.  
- **DB errors**: confirm `init.sql` ran and migrations match your schema.  
- **Redis errors**: check `REDIS_HOST`, `REDIS_PORT`, and optional password.  

More detail: [docs/setup.md](docs/setup.md), [docs/troubleshooting.md](docs/troubleshooting.md).
