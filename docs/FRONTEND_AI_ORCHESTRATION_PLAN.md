# Frontend Implementation Plan: AI Orchestration UI (v2.0)

> Implementation plan for integrating AI pipeline orchestration and brand equity
> visualization into the existing Next.js frontend (`ai-brand-automator-frontend`).

## Context

The Frontend Detailed Design Document (v2.0) specifies adding multi-tenant workspace
switching, real-time AI Thought-Tracing, an AI Assistant page, and ISO Brand Equity
dashboard views to the existing Next.js application.

After thorough codebase analysis, **most of the infrastructure already exists**.
This plan focuses only on the delta work required.

---

## Existing Infrastructure (No Changes Needed)

| Design Requirement | Status | Location |
|---|---|---|
| `X-Tenant-ID` interceptor in API client | Done | `src/lib/api.ts:77-83` |
| `TenantContext` with workspace switching | Done | `src/contexts/TenantContext.tsx` |
| `WorkspaceSwitcher` in sidebar | Done | `src/components/layout/WorkspaceSwitcher.tsx` |
| `ThoughtTrace` (real-time stepper) | Done | `src/components/pipelines/ThoughtTrace.tsx` |
| `BrandEquityDashboard` (SVG gauges) | Done | `src/components/pipelines/BrandEquityDashboard.tsx` |
| `usePollingJob` (3s poll) | Done | `src/hooks/usePollingJob.ts` |
| `useTenantRole` (RBAC helper) | Done | `src/hooks/useTenantRole.ts` |
| Orchestration API helpers | Done | `src/lib/orchestration.ts` |
| Pipeline types | Done | `src/types/orchestration.ts` |
| Pipeline detail page (graph + logs) | Done | `src/app/dashboard/pipelines/[jobId]/page.tsx` |
| Pipeline list + New Analysis modal | Done | `src/app/dashboard/pipelines/page.tsx` |
| `PipelineGraph` (React Flow DAG) | Done | `src/components/pipelines/PipelineGraph.tsx` |

---

## New Work Required

1. **`/dashboard/ai-assistant` page** -- Conversational AI chat + pipeline launcher
2. **`/dashboard/analysis` page** -- Historical brand equity reports list
3. **`/dashboard/analysis/[job_id]` page** -- Dedicated ISO valuation detail view
4. **NPV chart component** -- 5-year royalty relief forecast (pure SVG)
5. **Pillar radar chart component** -- BSI pillar comparison (pure SVG)
6. **`iso-formatters.ts`** -- Currency & NPV formatting helpers
7. **Enhanced `BrandEquityDashboard`** -- Add NPV valuation data and chart components
8. **Navigation updates** -- Add "AI Assistant" and "Reports" nav links

---

## Implementation Steps

### Step 1: Add `iso-formatters.ts` utility

**File:** `src/lib/utils/iso-formatters.ts` (NEW)

Provides:
- `formatCurrency(value, currency?)` -- e.g., `$1,137,236`
- `formatCompact(value)` -- e.g., `$1.1M`
- `formatPercent(value)` -- e.g., `4.0%`

Used by the NPV chart, analysis pages, and the enhanced BrandEquityDashboard.

### Step 2: Create NPV chart component

**File:** `src/components/dashboard/npv-chart.tsx` (NEW)

A pure SVG area/line chart showing the 5-year royalty relief forecast.
Input: `annual_royalties` array from `result_data.valuation`.
Matches the "Digital Twilight" theme with brand-electric gradient fill.

### Step 3: Create pillar radar chart component

**File:** `src/components/dashboard/pillar-radar.tsx` (NEW)

A pure SVG radar/spider chart comparing the 3 BSI pillars
(Financial, Behavioral, Legal). Input: `pillars` array from
`result_data.valuation.bsi.pillars` or the top-level `result_data` pillar scores.

### Step 4: Enhance `BrandEquityDashboard`

**File:** `src/components/pipelines/BrandEquityDashboard.tsx` (MODIFY)

Add:
- **Top bar**: Final Brand Valuation (NPV) and confidence score from `result_data.valuation`
- **NPV chart**: Render `NpvChart` when `result_data.valuation.annual_royalties` is present
- **Radar chart**: Render `PillarRadar` when BSI pillar data is present
- **Valuation metadata**: Royalty rate, discount rate, horizon years, methodology

### Step 5: Create `/dashboard/analysis` page (reports list)

**File:** `src/app/dashboard/analysis/page.tsx` (NEW)

Lists completed analysis jobs filtered to brand equity / ISO pipelines.
Reuses `listJobs()` from `src/lib/orchestration.ts`.
Shows score, NPV value, date, and status for each. Links to detail view.

### Step 6: Create `/dashboard/analysis/[job_id]` page (ISO detail)

**File:** `src/app/dashboard/analysis/[job_id]/page.tsx` (NEW)

Dedicated ISO valuation report view for completed jobs:
- **Top bar**: NPV value + confidence score
- **Grid**: BSI gauge (left) + NPV chart (center) + Radar chart (right)
- **Source sidebar**: Collapsible panel with grounding citations
- **Findings & recommendations**: Structured sections

Reuses `usePollingJob`, `getJob` from existing infrastructure.
Only renders the full dashboard when `status === 'completed'`.

### Step 7: Create `/dashboard/ai-assistant` page

**File:** `src/app/dashboard/ai-assistant/page.tsx` (NEW)

Single-page workflow combining:
- Inline prompt input area (similar to `NewAnalysisModal` but embedded)
- Pipeline manifest selector (auto-detect or specific)
- Active job tracking with `ThoughtTrace` (reuses existing component)
- Result display with `ResultDashboard` (reuses existing component)

Flow: enter prompt -> select pipeline -> run -> watch progress -> see results.
Uses existing `createJob`, `usePollingJob`, `ThoughtTrace`, and `ResultDashboard`.

### Step 8: Update Navigation

**File:** `src/components/common/Navigation.tsx` (MODIFY)

Add two new nav links to the `navLinks` array:
- `{ href: '/dashboard/ai-assistant', label: 'AI Assistant' }` -- visible to editors+
- `{ href: '/dashboard/analysis', label: 'Reports' }` -- visible to all members

---

## Files Summary

| # | File | Action | Description |
|---|------|--------|-------------|
| 1 | `src/lib/utils/iso-formatters.ts` | CREATE | Currency & NPV formatting helpers |
| 2 | `src/components/dashboard/npv-chart.tsx` | CREATE | Pure SVG area chart for 5-year NPV forecast |
| 3 | `src/components/dashboard/pillar-radar.tsx` | CREATE | Pure SVG radar chart for BSI pillar comparison |
| 4 | `src/components/pipelines/BrandEquityDashboard.tsx` | MODIFY | Add NPV valuation bar, charts, methodology info |
| 5 | `src/app/dashboard/analysis/page.tsx` | CREATE | Historical brand equity reports list |
| 6 | `src/app/dashboard/analysis/[job_id]/page.tsx` | CREATE | Dedicated ISO valuation detail view |
| 7 | `src/app/dashboard/ai-assistant/page.tsx` | CREATE | AI assistant + pipeline launcher |
| 8 | `src/components/common/Navigation.tsx` | MODIFY | Add AI Assistant & Reports nav links |

**Total: 5 new files, 2 modified files, 0 new npm dependencies**

---

## Key Design Decisions

### 1. No Recharts / chart library

The existing codebase uses pure SVG for all visualizations (RadialGauge in
BrandEquityDashboard, PipelineGraph via React Flow). We maintain this pattern to
keep the bundle lean and avoid adding a ~200KB dependency.

### 2. Reuse existing infrastructure

The design doc's core requirements (tenant context, API interceptor, workspace
switcher, thought trace, polling, orchestration API) are already implemented.
We build on top of these rather than duplicating.

### 3. `/dashboard/analysis` vs `/dashboard/pipelines`

The existing `/dashboard/pipelines` page shows all jobs (running + completed).
The new `/dashboard/analysis` page filters to completed brand equity jobs only,
providing a focused "reports" view. Both exist side by side.

### 4. AI Assistant as inline workflow

Rather than a separate chat system, the AI Assistant is a streamlined single-page
pipeline launcher that shows the full lifecycle: prompt -> execution -> results.

---

## Data Flow

```
User enters prompt in AI Assistant
       |
       v
POST /api/v1/orchestration/jobs/  (via createJob())
       |
       v
Backend dispatches to pipeline-orchestrator-svc
       |
       v
usePollingJob() polls GET /api/v1/orchestration/jobs/{job_id}/ every 3s
       |
       v
ThoughtTrace renders per-agent progress (pending -> running -> done)
       |
       v
On status=completed: ResultDashboard / BrandEquityDashboard renders results
       |
       v
result_data.valuation -> NpvChart (5-year forecast)
result_data.bsi       -> PillarRadar (3-pillar comparison)
result_data.score     -> RadialGauge (BSI central score)
```

---

## Backend API Endpoints Used

| Method | Endpoint | Used By |
|--------|----------|---------|
| `POST` | `/api/v1/orchestration/jobs/` | AI Assistant (create job) |
| `GET` | `/api/v1/orchestration/jobs/` | Analysis list page |
| `GET` | `/api/v1/orchestration/jobs/{job_id}/` | Job polling, detail pages |
| `POST` | `/api/v1/orchestration/jobs/{job_id}/cancel/` | AI Assistant (cancel) |
| `GET` | `/api/v1/orchestration/manifests/` | AI Assistant (pipeline selector) |

All endpoints require `Authorization: Bearer <token>` and `X-Tenant-ID` headers,
both of which are automatically injected by `src/lib/api.ts`.

---

## Verification

After implementation:
1. `cd ai-brand-automator-frontend && npm run build` -- No TypeScript errors
2. `npm run lint` -- ESLint passes
3. Manual testing:
   - `/dashboard/ai-assistant` -- page loads, prompt input works, pipeline runs
   - `/dashboard/analysis` -- page loads, shows completed brand equity jobs
   - `/dashboard/analysis/{job_id}` -- ISO dashboard with gauges + charts
   - `/dashboard/pipelines` -- existing page still works
   - Navigation shows "AI Assistant" and "Reports" links
   - WorkspaceSwitcher still functional
