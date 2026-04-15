# Backend Refactoring Guide

## 🎯 What Changed

The backend has been completely refactored from a monolithic structure to a proper layered architecture with:

### Architecture Improvements

**Before:**
- 650+ lines in main.py
- Blocking sync operations (video processing, downloads) in async context
- `asyncio.create_task()` for background jobs (lost on restart)
- No progress tracking
- Multiple database sessions per request
- No separation of concerns

**After:**
- **Layered Architecture**: routes → services → repositories
- **Async Job Queue**: arq (Redis-based) with persistent jobs
- **Separate Worker Process**: Video processing runs independently
- **Thread Pool**: Blocking operations don't block the event loop
- **Real-time Progress**: SSE (Server-Sent Events) + Redis pub/sub
- **Granular Status**: queued → downloading → transcribing → analyzing → generating_clips → completed

### New Directory Structure

```
backend/src/
├── api/routes/
│   ├── tasks.py           # Task endpoints + SSE
│   └── media.py           # Fonts, transitions, uploads
├── services/
│   ├── video_service.py   # Video processing logic
│   └── task_service.py    # Task orchestration
├── repositories/
│   ├── task_repository.py # Task DB operations
│   ├── clip_repository.py # Clip DB operations
│   └── source_repository.py
├── workers/
│   ├── tasks.py           # arq worker functions
│   ├── job_queue.py       # Queue management
│   └── progress.py        # Progress tracking
├── utils/
│   └── async_helpers.py   # Async wrappers
├── main_refactored.py     # New clean entry point
└── worker_main.py         # Worker process entry
```

## 🚀 Deployment Steps

### Step 1: Apply Database Migration

The refactoring adds `progress` and `progress_message` fields to the tasks table.

```bash
# Apply migration to existing database (use your connection string)
psql "$DATABASE_URL" -f backend/migrations/001_add_progress_fields.sql
```

For fresh installs, the updated `init.sql` already includes these fields.

### Step 2: Install New Dependencies

```bash
cd backend

# Install arq and redis
uv sync

# Or manually:
uv pip install arq>=0.26.0 redis>=5.0.0
```

### Step 3: Run API and worker locally

Use the refactored entry point and a separate ARQ worker process:

```bash
cd backend
source .venv/bin/activate
uvicorn src.main_refactored:app --reload --host 0.0.0.0 --port 8000
```

Second terminal:

```bash
cd backend
source .venv/bin/activate
arq src.workers.tasks.WorkerSettings
```

Ensure `DATABASE_URL`, `REDIS_HOST`, and API keys in `.env` match your environment.

## 🧪 Testing the Refactored System

### 1. Check Health Endpoints

```bash
# Basic health
curl http://localhost:8000/health

# Database health
curl http://localhost:8000/health/db

# Redis health (new!)
curl http://localhost:8000/health/redis
```

### 2. Create a Task

```bash
curl -X POST http://localhost:8000/tasks/ \
  -H "Content-Type: application/json" \
  -H "user_id: YOUR_USER_ID" \
  -d '{
    "source": {
      "url": "https://www.youtube.com/watch?v=VIDEO_ID"
    },
    "font_options": {
      "font_family": "TikTokSans-Regular",
      "font_size": 24,
      "font_color": "#FFFFFF"
    }
  }'
```

Response:
```json
{
  "task_id": "uuid-here",
  "job_id": "job-uuid",
  "message": "Task created and queued for processing"
}
```

### 3. Watch Real-time Progress (SSE)

```bash
curl -N http://localhost:8000/tasks/{task_id}/progress
```

You'll see streaming events like:
```
event: status
data: {"task_id":"...","status":"queued","progress":0,"message":""}

event: progress
data: {"task_id":"...","status":"processing","progress":10,"message":"Downloading video..."}

event: progress
data: {"task_id":"...","status":"processing","progress":30,"message":"Generating transcript..."}

... etc ...

event: close
data: {"status":"completed"}
```

### 4. Get Task Details

```bash
curl http://localhost:8000/tasks/{task_id}
```

### 5. Get Clips

```bash
curl http://localhost:8000/tasks/{task_id}/clips
```

## 📊 Monitoring Workers

### View worker / queue status

- Watch the terminal where `arq src.workers.tasks.WorkerSettings` runs.  
- Inspect Redis locally, for example:

```bash
redis-cli -h "${REDIS_HOST:-127.0.0.1}" -p "${REDIS_PORT:-6379}"
> KEYS arq:*
> LLEN arq:queue
```

### Check Job Status

The arq queue stores job status in Redis. You can inspect with:

```bash
redis-cli -h "${REDIS_HOST:-127.0.0.1}" -p "${REDIS_PORT:-6379}"
> KEYS arq:job:*
> GET arq:job:{job_id}
```

## 🔄 Rollback Plan

If issues arise, you can rollback:

### Option 1: Switch back to old main

Run the legacy entry point:

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Option 2: Keep Both Running

You can run both versions simultaneously on different ports for gradual migration:

- Old: `src.main:app` on port 8000
- New: `src.main_refactored:app` on port 8001

## 🎯 Performance Improvements

### Before Refactoring:
- ❌ Task page took 60+ seconds to show title
- ❌ Blocking operations stalled the entire server
- ❌ No progress visibility
- ❌ Jobs lost on restart

### After Refactoring:
- ✅ Instant task creation (< 100ms)
- ✅ Real-time progress updates
- ✅ Non-blocking API (video processing in workers)
- ✅ Persistent jobs survive restarts
- ✅ Horizontal scaling (add more workers)

## 🐛 Troubleshooting

### "Connection refused" to Redis

Check Redis is running and reachable from `REDIS_HOST` / `REDIS_PORT`:

```bash
redis-cli -h "${REDIS_HOST:-127.0.0.1}" -p "${REDIS_PORT:-6379}" ping
```

### Worker not processing jobs

1. Confirm the ARQ worker process is running (`arq src.workers.tasks.WorkerSettings`).  
2. Check Redis from Python (adjust host to match `.env`):

```bash
cd backend && source .venv/bin/activate
python -c "import os,redis; r=redis.Redis(host=os.environ.get('REDIS_HOST','127.0.0.1'), port=int(os.environ.get('REDIS_PORT',6379))); print(r.ping())"
```

### Database migration errors

If the migration fails, run it manually:
```sql
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS progress INTEGER DEFAULT 0;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS progress_message TEXT;
```

## 📝 Next Steps

1. **Update Frontend**: Consume SSE endpoint instead of polling
2. **Monitoring**: Add Prometheus metrics for job queue
3. **Scaling**: Deploy multiple worker instances for parallel processing
4. **Caching**: Add Redis caching for frequently accessed data
5. **Rate Limiting**: Protect API with rate limits

## 🔗 API Changes

### New Endpoints

- `POST /tasks/` - Create task (replaces `/start-with-progress`)
- `GET /tasks/{task_id}/progress` - SSE endpoint for real-time updates

### Deprecated Endpoints

- `POST /start` - Use `/tasks/` instead
- `POST /start-with-progress` - Use `/tasks/` instead

### Unchanged Endpoints

- `GET /tasks/{task_id}` - Still works
- `GET /tasks/{task_id}/clips` - Still works
- `GET /fonts` - Still works
- `GET /transitions` - Still works
- `POST /upload` - Still works
