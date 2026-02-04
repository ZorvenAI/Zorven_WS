# File Upload Feature Implementation Plan

> **Created:** February 4, 2026  
> **Status:** In Progress  
> **Branch:** feature/onboarding-pipeline-integration

## Overview

The dashboard's **"Upload Files"** quick action (`/files`) currently leads to a 404 error. This plan implements a dedicated file upload page that:
1. Allows users to upload brand assets
2. Integrates with the existing data pipeline (triggers `pipeline_service.publish_asset_event()`)
3. Shows upload progress and pipeline processing status

## Current State Analysis

| Component | Status | Location |
|-----------|--------|----------|
| Backend upload API | ✅ Exists | `POST /api/v1/assets/upload/` |
| Pipeline integration | ✅ Exists | `views.py` line 261 triggers `publish_asset_event()` |
| KongFileUploader component | ✅ Exists | `src/components/common/KongFileUploader.tsx` |
| AssetUploadForm component | ✅ Exists | `src/components/onboarding/AssetUploadForm.tsx` |
| `/files` page | ❌ Missing | Need to create `src/app/files/page.tsx` |

---

## Implementation Phases

### Phase 1: Create Files Page (Frontend)
**Status:** ✅ Complete

Create `/files` route with file upload functionality.

**File:** `src/app/files/page.tsx`
- Protected page (requires auth via `useAuth()`)
- Dashboard layout consistency
- Upload zone with drag & drop
- List of uploaded files with pipeline status
- Refresh/polling for pipeline status updates

---

### Phase 2: Create FileUploadManager Component (Frontend)
**Status:** ✅ Complete

A comprehensive file management component (separate from the onboarding flow).

**File:** `src/components/files/FileUploadManager.tsx`
- Multiple file upload support
- Progress indicators per file
- Pipeline status display (`pending` → `ingested` → `curated` → `indexed`)
- Error handling with retry option
- Real-time status updates (polling or WebSocket ready)

---

### Phase 3: Add Asset Status Endpoint (Backend)
**Status:** ✅ Complete

Add bulk status check endpoint for the frontend.

**File:** `onboarding/views.py` - Add action to `BrandAssetViewSet`
- `GET /api/v1/assets/status/` - Get assets with their pipeline statuses
- Filter by pipeline_status (pending, failed, etc.)

---

### Phase 4: Frontend Types & API Integration
**Status:** ✅ Complete

Add proper TypeScript types and API hooks.

**Files:**
- `src/types/assets.ts` - Type definitions for BrandAsset
- `src/hooks/useAssets.ts` - Custom hook for asset operations with polling

---

### Phase 5: Deployment
**Status:** ⏳ Ready for Deployment

Ensure seamless deployment to Railway (or your CI/CD pipeline).

**Steps:**
1. **Run Tests Locally**
   ```bash
   # Backend tests
   cd ai-brand-automator && pytest -v
   
   # Frontend tests
   cd ai-brand-automator-frontend && npm test
   ```

2. **Verify Black/Flake8 Formatting**
   ```bash
   cd ai-brand-automator && black . && flake8
   ```

3. **Commit & Push**
   ```bash
   git add .
   git commit -m "feat: Add file upload page with pipeline integration"
   git push origin <feature-branch>
   ```

4. **Create PR / Merge**
   - Create PR for code review
   - CI/CD runs tests automatically
   - Merge to main after approval

5. **Railway Deployment** (Auto-triggered on merge to main)
   - Backend: Django redeploys with new views
   - Frontend: Next.js redeploys with new `/files` route
   - No migrations needed (using existing BrandAsset model)

6. **Post-Deployment Verification**
   - Navigate to `/files` on production
   - Upload a test file
   - Verify pipeline status updates correctly
   - Check logs for any errors

---

## Detailed File Changes

| # | File | Action | Description |
|---|------|--------|-------------|
| 1 | `src/app/files/page.tsx` | **Create** | New files page with auth protection |
| 2 | `src/components/files/FileUploadManager.tsx` | **Create** | Upload manager with status tracking |
| 3 | `src/types/assets.ts` | **Create** | TypeScript types for assets |
| 4 | `src/hooks/useAssets.ts` | **Create** | Asset operations hook with polling |
| 5 | `onboarding/views.py` | **Modify** | Add `status` action to BrandAssetViewSet |
| 6 | `src/components/dashboard/QuickActions.tsx` | No change | Already points to `/files` |

---

## UI/UX Specifications

### Files Page Layout
```
┌─────────────────────────────────────────────┐
│  ← Back to Dashboard                        │
├─────────────────────────────────────────────┤
│  📁 Brand Assets                            │
│  Upload and manage your brand files         │
├─────────────────────────────────────────────┤
│  ┌─────────────────────────────────────┐    │
│  │  📤 Drop files here or click to    │    │
│  │     upload                          │    │
│  │  (images, PDFs, videos up to 50MB) │    │
│  └─────────────────────────────────────┘    │
├─────────────────────────────────────────────┤
│  Your Files                                 │
│  ┌──────────────────────────────────────┐   │
│  │ 🖼 logo.png    1.2MB  ✅ Indexed     │   │
│  │ 📄 guide.pdf   3.5MB  🔄 Processing  │   │
│  │ 🎬 intro.mp4  12.0MB  ❌ Failed [⟳]  │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

### Pipeline Status Indicators
- `pending` → 🕐 Pending
- `ingested` → 📥 Ingested  
- `curated` → ✨ Curated
- `indexed` → ✅ Indexed
- `failed` → ❌ Failed (with retry button)

---

## Estimated LOC

| File | Lines |
|------|-------|
| `files/page.tsx` | ~80 |
| `FileUploadManager.tsx` | ~250 |
| `types/assets.ts` | ~40 |
| `useAssets.ts` | ~80 |
| `views.py` changes | ~30 |
| **Total** | **~480** |

---

## Deployment Checklist

| Step | Command/Action | Verify |
|------|----------------|--------|
| 1. Run backend tests | `pytest -v` | All tests pass |
| 2. Run frontend tests | `npm test` | All tests pass |
| 3. Format code | `black .` | No changes needed |
| 4. Lint code | `flake8` | No errors |
| 5. Commit changes | `git commit -m "feat: ..."` | Clean commit |
| 6. Push to feature branch | `git push` | CI passes |
| 7. Create PR | GitHub/GitLab | Review approved |
| 8. Merge to main | Merge PR | Auto-deploy triggers |
| 9. Verify production | Visit `/files` | Upload works |
| 10. Monitor logs | Railway logs | No errors |

---

## Testing Strategy

1. **Unit tests:** New hooks and components
2. **Integration:** Upload → Pipeline trigger → Status webhook → UI update
3. **E2E:** Dashboard → Files → Upload → See processing status

---

## Progress Log

| Date | Phase | Status | Notes |
|------|-------|--------|-------|
| 2026-02-04 | Plan Created | ✅ | Initial implementation plan |
| 2026-02-04 | Phase 1 | ✅ | Created `/files` page with auth protection |
| 2026-02-04 | Phase 2 | ✅ | Created FileUploadManager component with drag & drop |
| 2026-02-04 | Phase 3 | ✅ | Added `/assets/status/` endpoint to backend |
| 2026-02-04 | Phase 4 | ✅ | Created types and hooks (assets.ts, useAssets.ts) |
| 2026-02-04 | Phase 5 | ⏳ | Ready for deployment - tests passing |
