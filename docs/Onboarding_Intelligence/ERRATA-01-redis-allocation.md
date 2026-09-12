# ERRATA-01 — Redis allocation for OIA

**Status:** Accepted correction. Read this before implementing anything that touches Redis.
**Date:** 2026-07-30
**Supersedes:** Backlog v2.0 story **A-04**; Design v2.1 **§4.2** and **§14** (Redis DB assignment only)
**Unchanged:** everything else in both documents

The source documents are binaries (`.pdf` / `.docx`) and cannot be edited in place, so corrections live here. Where this file and the PDFs disagree about Redis, **this file wins**.

---

## 1. The correction in one line

> OIA uses **Redis DB 2** with the `oia:v1:` key prefix. **Not DB 27.**

| | Design v2.1 says | Correct value |
|---|---|---|
| OIA session / live state | DB **27** (owned outright) | DB **2**, isolated by the `oia:v1:` prefix |
| Prompt cache (read-only) | DB 2, `poi:` prefix | unchanged — DB 2, `poi:` prefix |
| `config` → `redis_db:` | `27` | `2` |
| `app/cache/redis_manager.py` | "DB 27 pool" | DB 2 pool |
| Prerequisite | raise `databases` 27 → 28, restart Redis | **none** — no config change, no restart |

Both OIA's own state and the prompt cache it reads now live in the same database. Isolation is by key prefix, not by database index.

---

## 2. Why — DB 27 cannot exist in production

Production Redis is **Memorystore for Redis** (`zorven-redis`, BASIC tier, REDIS_7_0). Memorystore does **not** expose `databases` as a tunable `redisConfig`; the instance is fixed at **16 databases (0–15)**. There is no `redis.conf` to edit and no restart that changes it. DBs 16–26 do not exist there either — the fleet's documented 0–26 allocation was only ever valid under docker-compose, which starts Redis with `--databases 27`.

**The backlog predicted this exactly.** A-04's Technical Notes read:

> "If Redis is managed (Railway plugin, Redis Cloud) rather than self-hosted from a `redis.conf`, `databases` may not be operator-settable. Confirm this on day one of week 1. If it is not settable, the fallback is a key-prefix namespace on an existing DB rather than a dedicated DB — which changes every key pattern in Design §14 and makes `tests/test_redis_key_isolation.py` more important, not less. **Escalate immediately; do not silently pick DB 26.**"

That fallback branch is now the live path. The escalation happened, and this errata is its outcome.

### It was already breaking eleven services

This was not theoretical. Eleven services allocated DBs 16–26 had been failing in production with `ERR DB index is out of range` since at least **2026-07-25**:

`brand-positioning` (16), `brand-architecture` (17), `brand-personality` (18), `brand-naming` (19), `brand-story` (20), `campaign-architecture` (21), `creative-generation` (22), `ad-publishing` (23), `campaign-optimization` (24), `intelligence-loop` (25), `prompt-optimization` (26)

A-04 assumed `SELECT 27` would fail loudly at connection time and stop the service from starting. In practice the agent `RedisManager`s **fail open** — they log a warning and continue with no cache. So all eleven ran cacheless and silently for days. Anything OIA builds on Redis must not assume a bad DB index will announce itself.

Fixed in **PR #522** (script) and applied to the running services on 2026-07-30: all eleven remapped to DB 2 with prefix isolation. The root `CLAUDE.md` Redis allocation table now records the constraint — which also discharges A-04's final note ("update the monorepo CLAUDE.md Redis allocation table so the next service does not repeat this discovery").

---

## 3. What changes in the backlog

**A-04 · "Raise Redis `databases` to 28 across the shared instance" — drop it.** No `redis.conf` edit, no instance restart, no staging/production rollout window, no rollback plan. Its 2 points come out of Epic A.

Consequences:

- **A-05 is no longer blocked by A-04.** A-04 blocked "A-05, and transitively every story touching Redis" — that edge is gone, so Epic A shortens and every Redis-touching story is unblocked from week 1.
- **`tests/test_redis_key_isolation.py` becomes more important, not less** — exactly as A-04's notes warned. It is now the *only* mechanism keeping OIA's keys from colliding with ten other services sharing DB 2. It should assert that every key OIA writes begins with `oia:v1:`, and that OIA writes nothing under any other prefix.
- Anything asserting `CONFIG GET databases == 28` or a successful `SELECT 27` must be deleted rather than adapted.

---

## 4. What changes in Design §14

The key patterns in §14 are **already correctly prefixed** with `oia:v1:` and carry over unchanged — the table is sound, only the database index it sits in was wrong.

One exception. This key does not start with the service prefix:

```
tenant:{id}:oia:config        →  oia:v1:{tenant}:config
```

On a dedicated DB the generic `tenant:` prefix was harmless. On shared DB 2 it breaks the single-prefix invariant that `test_redis_key_isolation.py` enforces, and `tenant:`-rooted keys are used by other services on the same instance. Normalize it so **every** OIA key starts with `oia:v1:`.

Two properties of §14 that matter more now that the DB is shared:

- Every key must carry a TTL. §14 already assigns one to everything except `tenant:{id}:oia:config`; give the renamed key an explicit TTL or an explicit documented exemption. Memorystore applies `maxmemory-policy allkeys-lru` **instance-wide**, so an untrimmed OIA key can cause eviction pressure on other services' data.
- `oia:v1:circuit:{dep}` is deliberately not tenant-scoped. That stays correct — it just needs the `oia:v1:` prefix it already has, since circuit state for another service's dependency must not be readable as OIA's.

---

## 5. Local development is unaffected

`deployment/docker-compose.yml` still starts Redis with `--databases 27`, and the 0–26 allocation remains valid locally. Production and local therefore diverge, and the divergence is carried by environment variables (`OIA_REDIS_URL`), not by code defaults.

Set the service's default to the production-safe value so a missing env var fails safe:

```python
REDIS_URL: str = "redis://localhost:6379/2"    # not /27
```

---

## 6. Port 8120 — no longer a concern

Earlier notes flagged a collision with `spike-stt-v2`. That was overstated. `spike-stt-v2` is the **completed A-01 spike** (timeboxed, delivered in #495/#496). It is not in `docker-compose.yml`, not in CI, and not deployed to Cloud Run — 8120 is bound only when someone runs its `uvicorn` command by hand. OIA can take **8120** as designed; retiring the spike directory when OIA lands is tidy-up, not a prerequisite.

---

## 7. Checklist for the implementer

- [ ] `OIA_REDIS_URL` default is `redis://localhost:6379/2`
- [ ] `app/cache/redis_manager.py` opens a **DB 2** pool
- [ ] Every key written begins with `oia:v1:` — including the renamed `oia:v1:{tenant}:config`
- [ ] `tests/test_redis_key_isolation.py` asserts the prefix structurally, for every writer
- [ ] Every key has a TTL, or a documented reason it does not
- [ ] Prompt cache reads stay read-only against `poi:` in DB 2
- [ ] A-04 removed from Epic A; A-05's dependency edge on it deleted
- [ ] No test asserts `databases == 28` or `SELECT 27`
