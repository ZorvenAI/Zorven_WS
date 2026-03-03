# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this service.

## What This Service Does

`brand-equity-calculator-svc` is a FastAPI microservice (port 8090) that provides public, unauthenticated brand equity evaluation based on ISO 20671:2019 (Brand evaluation — Principles and fundamentals). Uses Anthropic Claude Opus 4.6 to analyze company brand equity across five dimensions: Governance, Engagement, Perception, Financial Performance, and Protection.

## Build & Run Commands

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload

# Tests
pytest tests/ -v
pytest tests/ -m "not integration" -v

# Format
black app/ tests/
```

## Architecture

- `app/api/` — Routes (POST /v1/calculate, GET /health) + Pydantic schemas
- `app/core/` — Config (BRAND_EQUITY_ prefix), logging
- `app/cache/` — RedisManager (result cache 24h, IP rate limiting 5/min)
- `app/services/` — BrandEquityExecutor (orchestrator), ClaudeClient (Anthropic wrapper)

## Key Contracts

**POST /v1/calculate** — public, no auth
```json
Request:  { company_name, address, website, industry_type, business_size, scope }
Response: { overall_score, dimensions[], formula_explanation, derivation, limitations[], recommendations[], methodology }
```

Returns 503 if ANTHROPIC_API_KEY is not configured. Returns 429 if rate limited.

## Environment Variables

All prefixed with `BRAND_EQUITY_`:
- `ANTHROPIC_API_KEY` — required for real analysis (503 if missing)
- `REDIS_URL` — default redis://localhost:6379/8
- `CLAUDE_MODEL` — default claude-opus-4-6
- `RATE_LIMIT_PER_MINUTE` — default 5
- `RESULT_CACHE_TTL` — default 86400 (24h)
- `PORT` — default 8090

## Redis Key Patterns

- `equity:result:{md5(key)}` — 24h TTL
- `equity:rate:{ip}` — 60s TTL
