#!/bin/bash

# SupoClip — print local run checklist (no container orchestration in-repo)

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "============================================"
echo "  SupoClip — local development checklist"
echo "============================================"
echo ""

if [ ! -f .env ]; then
    echo -e "${RED}Error: .env file not found.${NC}"
    echo "  cp .env.example .env"
    echo "  Then set ASSEMBLY_AI_API_KEY and an LLM provider key (or Ollama)."
    exit 1
fi

# shellcheck source=/dev/null
source .env

if [ -z "$ASSEMBLY_AI_API_KEY" ]; then
    echo -e "${YELLOW}Warning: ASSEMBLY_AI_API_KEY is not set.${NC}"
fi

if [ -z "$OPENAI_API_KEY" ] && [ -z "$GOOGLE_API_KEY" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
    if [[ "${LLM:-}" != ollama:* ]]; then
        echo -e "${YELLOW}Warning: No hosted LLM API key set (or LLM=ollama:...).${NC}"
    fi
fi

echo -e "${GREEN}Prerequisites (run on your machine):${NC}"
echo "  • PostgreSQL 15+ listening (see DATABASE_URL in .env)"
echo "  • Redis listening (REDIS_HOST / REDIS_PORT in .env)"
echo "  • ffmpeg on PATH"
echo ""
echo "  Initialize schema once, from repo root:"
echo "    psql \"\$DATABASE_URL\" -f init.sql"
echo "    # plus backend/migrations/*.sql if your DB predates them"
echo ""
echo -e "${GREEN}Run these in separate terminals:${NC}"
echo ""
echo "  1) Backend API"
echo "     cd backend && uv sync && source .venv/bin/activate"
echo "     uvicorn src.main_refactored:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "  2) Worker (required for video jobs)"
echo "     cd backend && source .venv/bin/activate"
echo "     arq src.workers.tasks.WorkerSettings"
echo ""
echo "  3) Frontend"
echo "     cd frontend && npm install && npm run dev"
echo ""
echo "Then open http://localhost:3000 (API docs: http://localhost:8000/docs)"
echo "============================================"
