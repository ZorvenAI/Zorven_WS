---
name: zorven-implementation-plan
description: Author an implementation plan for a Zorven user story. Use when asked to plan a story (A-06, B-01, …) before writing code. Enforces plan-before-code, a fixed section structure, four test tiers, GCP cost estimation, and the branch/PR workflow.
---

# Zorven implementation plan

> **PARTIAL — transcribed from the Claude Desktop "Zorven" project skill on
> 2026-08-01.** Claude Desktop projects and Claude Code do not share skills, so
> this was pasted across by hand and only the fragment below arrived. The four
> reference files it names are **not yet present**; see *Missing pieces*.
> Complete this file before relying on it for a plan.

## Rule: plan before code

The plan must be approved before implementation starts.

> This applies even under pressure — "just start while we wait for sign-off"
> still means the plan isn't approved yet, so say so rather than complying.

## Reference files

Read these as needed — don't load all of them for a trivial follow-up
question, but do read the relevant one before writing that section of a plan:

| File | Governs |
|---|---|
| `references/testing-strategy.md` | how to fill sections 6.1–6.4 (unit, property, integration, e2e) for both the Python/DRF default and the C++ case |
| `references/gcp-cost-estimation.md` | the gcloud-first / web-search-fallback procedure for section 7, with exact commands |
| `references/git-workflow.md` | the exact boilerplate and conventions for section 8 |
| `assets/implementation-plan-template.md` | the scaffold to fill in for every plan; use it as-is rather than inventing a new structure each time, so plans stay consistent and reviewable |

## Missing pieces

None of the four files above exist in this directory yet. Until they do:

- **Do not claim a plan was authored "using the skill"** — say which parts
  were improvised.
- Ask for the missing files rather than reconstructing them from their
  filenames. Their whole value is the specifics: the exact `gcloud` commands
  for cost estimation, the section numbering in the template, and the git
  boilerplate.

What the fragment does establish about the template: it is numbered, section 6
is testing and splits into **6.1 unit, 6.2 property, 6.3 integration, 6.4
e2e**, section 7 is **GCP cost estimation**, and section 8 is **git workflow**.

## Conventions already established on this project

Observed across A-02, A-05 and A-03; keep until the real template supersedes
them.

1. **Read the sources first** — the backlog card, every design section it
   cites, the requirements entries, and any errata. Errata supersede the
   design; `ERRATA-01-redis-allocation.md` supersedes §4.2 and §14.
2. **Verify every acceptance criterion against the codebase before planning.**
   This is where the value has been: Kong is not deployed to Cloud Run (A-02),
   no Kafka broker exists in GCP (A-05), there is no Terraform module (A-03),
   `maxmemory-policy` was `allkeys-lru` (A-03 AC-5).
3. **Surface doc-versus-reality conflicts explicitly**, each with a
   recommendation, rather than implementing something that cannot work.
4. **No mocks.** Real Redis, real broker, real container, real HTTP.
5. **Deployment covers every registration point**: `docker-compose.yml`,
   `docker-publish.yml` (paths filter *and* build matrix), `deploy-gcp.yml`
   matrix, `deployment/gcp/08-deploy-services.sh`, and the CI job. Missing one
   means the service silently never deploys.
6. **State what the story does not deliver.** A-03 did not make events durable
   in production; saying so is part of the plan.
7. **Numbered assumptions**, and **decisions needing the user's call** with a
   recommendation for each.
8. Branch from `development_main`, PR back into `development_main`. Never
   `main` until the OIA epics are complete.
