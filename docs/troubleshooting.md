# Troubleshooting

Common operational issues and how to diagnose them.

## Start here

Verify:

- `http://localhost:3000` loads  
- `http://localhost:8000/health` responds  
- `http://localhost:8000/docs` opens  

Check the terminals where you run **backend** (`uvicorn`), **worker** (`arq`), and **frontend** (`npm run dev`) for errors.

## Processes fail to start

### Symptom

API, worker, or Next.js exits immediately or loops on errors.

### Common causes

- `.env` is missing or incomplete  
- PostgreSQL or Redis not running or wrong `DATABASE_URL` / `REDIS_*`  
- Invalid `NEXT_PUBLIC_*` build-time variables  
- Missing Python/Node dependencies (`uv sync`, `npm install`)  

### Fixes

- Confirm Postgres accepts connections: `psql "$DATABASE_URL" -c 'select 1'`  
- Confirm Redis: `redis-cli -h "$REDIS_HOST" -p "${REDIS_PORT:-6379}" ping`  
- Restart backend and worker after changing `.env`  

## Tasks stay queued forever

### Symptom

Task creation succeeds, but progress never moves beyond `queued`.

### Most likely causes

- ARQ worker is not running  
- Redis is unavailable  
- `QUEUED_TASK_TIMEOUT_SECONDS` elapsed while stuck  

### Checks

- Worker terminal: exceptions or import errors  
- Redis connectivity  
- Task row status in PostgreSQL  

### Fixes

- From `backend/`: `arq src.workers.tasks.WorkerSettings`  
- Fix Redis host/port/password  
- Review worker logs around enqueue and `process_video_task`  

## Backend starts but clip generation fails

### Symptom

Tasks move to `error` during processing.

### Common causes

- Invalid API keys  
- LLM/provider mismatch  
- YouTube download / Apify issues  
- AssemblyAI failure  
- FFmpeg or media stack errors  
- Font or template issues  

### Checks

- Backend and worker terminal output  
- `ASSEMBLY_AI_API_KEY` and `LLM` + provider key alignment  

### Provider mismatch examples

- `LLM=openai:...` requires `OPENAI_API_KEY`  
- `LLM=google-gla:...` requires `GOOGLE_API_KEY`  
- `LLM=anthropic:...` requires `ANTHROPIC_API_KEY`  
- `LLM=ollama:...` requires a reachable Ollama endpoint  

## YouTube downloads fail

### Common causes

- Network or anti-bot restrictions  
- Missing `APIFY_API_TOKEN` when that path is expected  
- `yt-dlp` edge cases  

### Checks

- Backend/worker logs  
- `APIFY_YOUTUBE_DEFAULT_QUALITY` is one of `360`, `480`, `720`, or `1080`  

### Fixes

- Ensure URL is publicly reachable  
- Configure `APIFY_API_TOKEN` if using Apify as primary downloader  

## Frontend loads but shows errors

### Common causes

- Backend unreachable from browser  
- Wrong `NEXT_PUBLIC_API_URL`  
- Auth secret or origin mismatch  
- Schema not applied  

### Fixes

- Point `NEXT_PUBLIC_API_URL` at the API  
- Align `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL`, and trusted origins  

## Cannot sign in or sign up

### Common causes

- PostgreSQL down or wrong `DATABASE_URL`  
- Better Auth misconfiguration  
- `DISABLE_SIGN_UP=true`  
- Cookie / HTTPS / origin mismatch  

### Checks

- `users` / `session` tables exist  
- App URL matches `BETTER_AUTH_URL`  

## Fonts are missing or upload fails

- Files under `backend/fonts/`  
- `GET /fonts` and frontend `/api/fonts`  

## Caption templates or B-roll

- `GET /caption-templates`  
- `PEXELS_API_KEY` and `GET /broll/status`  

## Billing or subscription flow

See [Configuration](./configuration.md): `SELF_HOST=false`, Stripe, `BACKEND_AUTH_SECRET`, Resend.

## Database problems

### Checks

- Postgres running and `DATABASE_URL` correct  
- `init.sql` applied; `backend/migrations/*.sql` on older DBs  

### Clean reset (local dev only)

Drop and recreate the database (or re-run `init.sql` on a fresh DB). **This destroys data.**

## Redis problems

### Symptom

Queueing, progress SSE, or worker behavior breaks.

### Checks

```bash
redis-cli -h "${REDIS_HOST:-127.0.0.1}" -p "${REDIS_PORT:-6379}" ping
```

## Performance is poor

- `DEFAULT_PROCESSING_MODE=fast`  
- `FAST_MODE_MAX_CLIPS`  
- Lighter transcript model settings  
- `GET /tasks/metrics/performance`  

## Task page never shows completed clips

- `GET /tasks/{task_id}` and clips endpoints  
- SSE / network tab  
- Worker finished without error  

## Admin features

- `is_admin` on user row  
- Admin routes and session  

## Recovery playbook

1. Stop `uvicorn`, `arq`, and `npm run dev`.  
2. Review `.env`.  
3. Verify Postgres + Redis.  
4. Restart backend, worker, then frontend.  

## Before filing an issue

- Commands you ran  
- Redacted `.env` keys involved  
- Browser errors  
- Backend and worker log excerpts  
- YouTube vs upload  
- `SELF_HOST` value  

## Related reading

- [Setup](./setup.md)  
- [Configuration](./configuration.md)  
- [Architecture](./architecture.md)  
