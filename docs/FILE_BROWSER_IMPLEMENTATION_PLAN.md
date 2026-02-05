# Implementation Plan: Enhanced File Browser for Onboarding

## Overview
Transform the current file list into a full-featured file browser with pagination, search, filtering, sorting, and secure file access via signed URLs.

---

## Phase 1: Backend API Enhancements

### 1.1 Signed URL Generation Endpoint
**File:** `onboarding/views.py`

- Add new endpoint: `GET /api/v1/assets/{id}/signed-url/`
- Generate temporary signed URL (15-minute expiry) for viewing/downloading
- Return both `view_url` and `download_url` (with content-disposition header)

```json
Response: {
  "view_url": "https://storage.googleapis.com/...",
  "download_url": "https://storage.googleapis.com/...",
  "expires_at": "2026-02-05T12:30:00Z"
}
```

### 1.2 Enhanced Assets List Endpoint
**File:** `onboarding/views.py`

Enhance existing `GET /api/v1/assets/` with query parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | int | Page number (1-indexed, default: 1) |
| `page_size` | int | Items per page (default: 10, max: 50) |
| `limit` | int | Quick limit for onboarding view (3, 6, 9) |
| `search` | string | Search by filename |
| `file_type` | string | Filter: image, video, document, other |
| `status` | string | Filter: pending, indexed, failed |
| `sort_by` | string | Field: uploaded_at, file_name, file_size |
| `sort_order` | string | asc or desc (default: desc) |

### 1.3 GCS Service Enhancement
**File:** `files/services.py`

Add method to `GCSService`:
- `generate_signed_url(gcs_path, expiration_minutes=15, for_download=False)`
- Use Google Cloud Storage's `generate_signed_url()` method

---

## Phase 2: Frontend Components

### 2.1 File Browser Component Structure

```
AssetUploadForm.tsx (Onboarding - Limited View)
├── FileUploadZone (existing drag-drop area)
├── FileFiltersBar (NEW - compact version)
│   ├── LimitSelector (3/6/9 buttons)
│   └── ViewAllButton → opens /files or modal
├── FileList (ENHANCED - scrollable, max 9 items)
│   ├── FileRow (with view/download/delete actions)
│   └── LoadingState / EmptyState
└── Navigation buttons (Back/Skip/Next)

AllFilesModal.tsx (Full Page or Modal - Paginated)
├── FileFiltersBar (FULL version)
│   ├── SearchInput
│   ├── FileTypeFilter (dropdown)
│   ├── StatusFilter (dropdown)
│   ├── SortDropdown
│   └── PageSizeSelector (10/25/50)
├── FileList (scrollable, shows page_size items)
│   ├── FileRow (with view/download/delete actions)
│   └── LoadingState / EmptyState
├── PaginationControls (NEW)
│   ├── PageInfo ("Showing 1-10 of 45")
│   ├── PrevButton
│   ├── PageNumbers (1, 2, 3, ..., 5)
│   └── NextButton
└── BackButton (return to onboarding)
```

### 2.2 New UI Features

#### Limit Selector (Onboarding View - Segmented Control)
```
[ 3 ] [ 6 ] [ 9 ] [View All →]
```

#### Search Bar
- Debounced search (300ms delay)
- Placeholder: "Search files..."
- Clear button when text present

#### Filter Dropdowns
- **File Type:** All, Images, Videos, Documents
- **Status:** All, Pending, Indexed, Failed

#### Sort Options
- Date (Newest/Oldest)
- Name (A-Z/Z-A)
- Size (Largest/Smallest)

#### Page Size Selector (All Files View)
```
Show: [ 10 ▼ ] [ 25 ] [ 50 ] per page
```

#### Pagination Controls (All Files View)
```
Showing 1-10 of 45 files    [←] [1] [2] [3] ... [5] [→]
```

Features:
- Previous/Next arrows (disabled at boundaries)
- Page numbers with ellipsis for many pages
- Current page highlighted
- Jump to first/last page
- Keyboard navigation (arrow keys)

#### File Row Actions
Each file row will have:
- 👁️ View (opens in new tab via signed URL)
- ⬇️ Download (triggers download via signed URL)
- 🗑️ Delete (existing functionality)

### 2.3 Scrollable Container
- Max height: 400px (onboarding), 600px (all files)
- Custom scrollbar styling to match dark theme
- Smooth scroll behavior

---

## Phase 3: File Structure Changes

### Backend Files to Modify:
1. `files/services.py` - Add signed URL generation
2. `onboarding/views.py` - Add signed URL endpoint + query params + pagination
3. `onboarding/urls.py` - Register new endpoint

### Frontend Files to Modify:
1. `src/components/onboarding/AssetUploadForm.tsx` - Compact file browser
2. `src/lib/api.ts` - Add `getSignedUrl()` helper function

### New Frontend Files to Create:
1. `src/components/files/FileFiltersBar.tsx` - Search, filters, sort controls
2. `src/components/files/FileListItem.tsx` - Individual file row with actions
3. `src/components/files/Pagination.tsx` - Pagination controls component
4. `src/components/files/AllFilesModal.tsx` - Modal for viewing all files
5. `src/hooks/useFileFilters.ts` - State management for filters
6. `src/hooks/usePagination.ts` - Pagination state and logic

---

## Phase 4: Implementation Order

| Step | Task | Estimated Effort | Status |
|------|------|------------------|--------|
| 1 | Add signed URL generation to GCSService | Small | ⬜ |
| 2 | Add signed URL API endpoint | Small | ⬜ |
| 3 | Enhance assets list with query params + pagination | Medium | ⬜ |
| 4 | Create `Pagination` component | Medium | ⬜ |
| 5 | Create `FileFiltersBar` component | Medium | ⬜ |
| 6 | Create `FileListItem` component | Medium | ⬜ |
| 7 | Refactor `AssetUploadForm` with compact view | Medium | ⬜ |
| 8 | Create `AllFilesModal` | Large | ⬜ |
| 9 | Add scrollable container styling | Small | ⬜ |
| 10 | Wire up pagination with API | Medium | ⬜ |
| 11 | Test and polish | Medium | ⬜ |

---

## Phase 5: API Response Shape

### Enhanced Assets List Response (Paginated)
```json
{
  "count": 45,
  "total_pages": 5,
  "current_page": 1,
  "page_size": 10,
  "has_next": true,
  "has_previous": false,
  "next": "/api/v1/assets/?page=2&page_size=10",
  "previous": null,
  "results": [
    {
      "id": 29,
      "file_name": "video.mp4",
      "file_type": "video",
      "file_size": 15000000,
      "pipeline_status": "indexed",
      "uploaded_at": "2026-02-05T10:30:00Z",
      "thumbnail_url": null
    }
  ],
  "filters_applied": {
    "search": null,
    "file_type": null,
    "status": null,
    "sort_by": "uploaded_at",
    "sort_order": "desc"
  }
}
```

### Quick Limit Response (For Onboarding)
When using `?limit=6` instead of pagination:
```json
{
  "count": 45,
  "showing": 6,
  "results": [...],
  "has_more": true
}
```

---

## Phase 6: Security Considerations

1. **Signed URLs expire in 15 minutes** - prevents link sharing
2. **User must be authenticated** to request signed URLs
3. **Tenant isolation** - users can only access their own files
4. **Rate limiting** on signed URL generation (optional)
5. **Page size capped at 50** - prevents excessive data fetching

---

## Phase 7: Testing Strategy

### 7.1 Backend Unit Tests
**File:** `onboarding/tests/test_file_browser.py`

| Test Case | Description |
|-----------|-------------|
| `test_signed_url_generation` | Verify GCSService generates valid signed URLs |
| `test_signed_url_expiry` | Verify URL includes correct expiration time |
| `test_signed_url_unauthorized` | Verify 401 for unauthenticated requests |
| `test_signed_url_wrong_tenant` | Verify 404 when accessing another tenant's file |
| `test_assets_list_search` | Verify search parameter filters by filename |
| `test_assets_list_file_type_filter` | Verify file_type filter works correctly |
| `test_assets_list_status_filter` | Verify status filter works correctly |
| `test_assets_list_sort_by_date` | Verify sorting by uploaded_at (asc/desc) |
| `test_assets_list_sort_by_name` | Verify sorting by file_name (asc/desc) |
| `test_assets_list_sort_by_size` | Verify sorting by file_size (asc/desc) |
| `test_assets_list_limit` | Verify limit parameter (3, 6, 9) |
| `test_assets_list_combined_filters` | Verify multiple filters work together |
| `test_pagination_first_page` | Verify page=1 returns correct items |
| `test_pagination_middle_page` | Verify page=3 returns correct offset |
| `test_pagination_last_page` | Verify last page has correct item count |
| `test_pagination_out_of_bounds` | Verify page=999 returns empty or error |
| `test_pagination_page_size` | Verify page_size=25 returns 25 items |
| `test_pagination_max_page_size` | Verify page_size>50 is capped at 50 |
| `test_pagination_with_filters` | Verify pagination works with search/filters |
| `test_pagination_metadata` | Verify has_next, has_previous, total_pages correct |

### 7.2 Backend Integration Tests
**File:** `onboarding/tests/test_file_browser_integration.py`

| Test Case | Description |
|-----------|-------------|
| `test_signed_url_with_real_gcs` | Test actual GCS signed URL (use mock in CI) |
| `test_full_upload_and_browse_flow` | Upload file → List → Get signed URL → Verify accessible |
| `test_delete_then_list` | Delete file → Verify removed from list |
| `test_pagination_consistency` | Navigate pages → no duplicates or missing items |

### 7.3 Frontend Unit Tests

**File:** `src/components/files/__tests__/FileFiltersBar.test.tsx`

| Test Case | Description |
|-----------|-------------|
| `renders search input` | Search bar visible and functional |
| `debounces search input` | Search triggers after 300ms delay |
| `renders file type dropdown` | File type filter options correct |
| `renders status dropdown` | Status filter options correct |
| `renders limit selector` | 3/6/9/All buttons render correctly |
| `calls onChange when filter changes` | Callback triggered on filter change |

**File:** `src/components/files/__tests__/FileListItem.test.tsx`

| Test Case | Description |
|-----------|-------------|
| `renders file info correctly` | Name, size, type, status displayed |
| `shows view button` | View icon visible |
| `shows download button` | Download icon visible |
| `shows delete button` | Delete icon visible |
| `calls onView when view clicked` | View handler triggered |
| `calls onDownload when download clicked` | Download handler triggered |
| `calls onDelete when delete clicked` | Delete handler triggered with confirmation |
| `shows loading state during delete` | Spinner shown during delete operation |

**File:** `src/components/files/__tests__/Pagination.test.tsx`

| Test Case | Description |
|-----------|-------------|
| `renders page info correctly` | "Showing 1-10 of 45" displayed |
| `renders correct number of page buttons` | Page buttons match total_pages |
| `highlights current page` | Current page visually distinct |
| `disables prev on first page` | Prev button disabled when page=1 |
| `disables next on last page` | Next button disabled on last page |
| `calls onPageChange when clicking page` | Handler receives correct page number |
| `shows ellipsis for many pages` | "..." shown between 3 and last page |
| `handles single page` | No pagination shown for 1 page |
| `keyboard navigation works` | Arrow keys change pages |

**File:** `src/components/onboarding/__tests__/AssetUploadForm.test.tsx`

| Test Case | Description |
|-----------|-------------|
| `renders file browser with filters` | All filter components visible |
| `fetches files with default params` | Initial API call correct |
| `updates list when filter changes` | API called with new params |
| `scrollable container has max height` | Container CSS correct |
| `polling updates file status` | Status refreshes automatically |
| `limit selector changes displayed count` | 3/6/9 works correctly |
| `view all button opens modal` | Click triggers modal open |

**File:** `src/components/files/__tests__/AllFilesModal.test.tsx`

| Test Case | Description |
|-----------|-------------|
| `renders with pagination` | Pagination controls visible |
| `loads first page on open` | API called with page=1 |
| `changes page on pagination click` | New page loaded |
| `filters persist across pages` | Search/filter maintained |
| `page size change resets to page 1` | Changing page_size goes to first page |
| `close button works` | Modal closes on click |

### 7.4 Frontend Integration Tests (E2E with Playwright/Cypress)
**File:** `e2e/file-browser.spec.ts`

| Test Case | Description |
|-----------|-------------|
| `upload and see file in list` | Full upload flow visible in browser |
| `search filters files` | Type in search → list updates |
| `filter by file type` | Select filter → only matching files shown |
| `sort files by date` | Change sort → order changes |
| `view file opens signed URL` | Click view → new tab opens with file |
| `download file triggers download` | Click download → file downloads |
| `delete file removes from list` | Confirm delete → file gone |
| `limit selector changes count` | Select 3 → only 3 files shown |
| `view all opens full browser` | Click View All → modal opens |
| `pagination navigates pages` | Click page 2 → different files shown |
| `pagination prev/next work` | Arrow buttons navigate correctly |
| `page size changes item count` | Select 25 → 25 items per page |
| `filters work with pagination` | Filter + paginate shows correct results |

### 7.5 Test Commands

```bash
# Backend tests
cd ai-brand-automator
pytest onboarding/tests/test_file_browser.py -v
pytest onboarding/tests/test_file_browser_integration.py -v --run-integration

# Frontend tests
cd ai-brand-automator-frontend
npm test -- --testPathPattern="FileFiltersBar|FileListItem|AssetUploadForm|Pagination|AllFilesModal"

# E2E tests
npm run test:e2e -- --spec="e2e/file-browser.spec.ts"
```

---

## Phase 8: Deployment

### 8.1 Environment Variables

**New variables needed (if not already set):**

```bash
# Backend (.env)
GCS_SIGNED_URL_EXPIRY_MINUTES=15  # Optional, defaults to 15
DEFAULT_PAGE_SIZE=10              # Optional, defaults to 10
MAX_PAGE_SIZE=50                  # Optional, defaults to 50

# No new frontend env vars required - uses existing NEXT_PUBLIC_API_URL
```

### 8.2 GCS Service Account Permissions

Ensure the service account has permission to generate signed URLs:
- `storage.objects.get` (already required for uploads)
- Service account key must be available (already configured)

### 8.3 Deployment Steps (Local Docker)

```bash
# 1. Rebuild backend (includes new API endpoints)
cd ai-brand-automator
docker compose build --no-cache backend

# 2. Rebuild frontend (includes new components)
docker compose build --no-cache frontend

# 3. Restart services
docker compose up -d backend frontend

# 4. Verify backend is healthy
docker ps --filter "name=backend" --format "{{.Names}}: {{.Status}}"

# 5. Verify frontend is healthy
docker ps --filter "name=frontend" --format "{{.Names}}: {{.Status}}"

# 6. Run smoke tests
# Test pagination
curl -s "http://localhost:8000/api/v1/assets/?page=1&page_size=10" -H "Authorization: Bearer $TOKEN"

# Test quick limit
curl -s "http://localhost:8000/api/v1/assets/?limit=6" -H "Authorization: Bearer $TOKEN"

# Test filters with pagination
curl -s "http://localhost:8000/api/v1/assets/?page=1&search=video&file_type=video" -H "Authorization: Bearer $TOKEN"
```

### 8.4 Deployment Steps (Railway Production)

```bash
# 1. Commit all changes
git add .
git commit -m "feat: Enhanced file browser with pagination, search, filters, signed URLs"

# 2. Push to trigger Railway deployment
git push origin main

# 3. Monitor Railway dashboard for build status

# 4. Verify production endpoints
curl -s "https://your-app.railway.app/api/v1/assets/?page=1&page_size=10" \
  -H "Authorization: Bearer $PROD_TOKEN"
```

### 8.5 Rollback Plan

If issues arise:

```bash
# Local rollback
git revert HEAD
docker compose build --no-cache backend frontend
docker compose up -d

# Railway rollback
# Use Railway dashboard → Deployments → Rollback to previous
```

### 8.6 Pre-Deployment Checklist

| Item | Status |
|------|--------|
| All backend tests passing | ✅ Created (27 tests in test_file_browser.py) |
| All frontend tests passing | ✅ Created (5 test files) |
| E2E tests passing | ✅ Created (file-browser.spec.ts) |
| GCS signed URL working locally | ⬜ Run smoke test |
| Pagination working correctly | ⬜ Run smoke test |
| Docker builds successful | ⬜ Run `docker compose build` |
| No console errors in browser | ⬜ Manual check |
| Responsive design verified | ⬜ Manual check |
| Code review completed | ⬜ Review this implementation |

### 8.7 Post-Deployment Verification

| Check | Command/Action |
|-------|----------------|
| Backend health | `curl /health/` returns 200 |
| Assets list works | `GET /api/v1/assets/` returns files |
| Pagination works | `GET /api/v1/assets/?page=2` returns page 2 |
| Search works | `GET /api/v1/assets/?search=test` filters correctly |
| Signed URL works | `GET /api/v1/assets/{id}/signed-url/` returns valid URL |
| Frontend loads | Navigate to onboarding step 4, file browser visible |
| Limit selector works | Click 3/6/9, correct number of files shown |
| View All works | Opens modal with pagination |
| Pagination UI works | Navigate between pages |
| Upload works | Upload new file, appears in list |
| Delete works | Delete file, removed from list |

---

## Design Decisions

### View All Behavior
- Opens as a **modal overlay** (not a separate page)
- Keeps user in onboarding context
- Easy to close and return

### File Preview
- Clicking "View" opens file in **new browser tab** via signed URL
- Simple, works for all file types
- No in-app preview modal (reduces complexity)

### Thumbnails
- **Not included** in initial implementation
- Can be added later as enhancement

### Bulk Actions
- **Not included** in initial implementation
- Single file operations only

### URL State
- Pagination and filters **not persisted in URL** for modal
- Modal state is ephemeral

---

## Progress Tracking

### Phase 1: Backend API ✅ COMPLETE
- [x] 1.1 Signed URL generation in GCSService - `files/services.py`
- [x] 1.2 Signed URL API endpoint - `onboarding/views.py`
- [x] 1.3 Enhanced assets list with filters/pagination - `onboarding/views.py`

### Phase 2: Frontend Components ✅ COMPLETE
- [x] 2.1 FileFiltersBar component - `src/components/ui/FileFiltersBar.tsx`
- [x] 2.2 FileListItem component - `src/components/files/FileListItem.tsx`
- [x] 2.3 Pagination component - `src/components/ui/Pagination.tsx`
- [x] 2.4 AllFilesModal component - `src/components/ui/AllFilesModal.tsx`
- [x] 2.5 Update AssetUploadForm - `src/components/onboarding/AssetUploadForm.tsx`

### Phase 3: File Structure ✅ COMPLETE
- [x] 3.1 API helpers - `src/lib/api.ts` (assetsApi, getSignedUrl, getAssets)
- [x] 3.2 Custom hooks - `src/hooks/useFileFilters.ts`, `src/hooks/usePagination.ts`

### Phase 4-6: Verification ✅ COMPLETE
- [x] Implementation order verified
- [x] API response shape verified
- [x] Security considerations verified (15min expiry, auth, tenant isolation, page cap)

### Phase 7: Testing ✅ COMPLETE
- [x] 7.1 Backend unit tests - `onboarding/tests/test_file_browser.py`
- [x] 7.2 Backend integration tests - `onboarding/tests/test_file_browser_integration.py`
- [x] 7.3 Frontend unit tests:
  - `src/components/ui/__tests__/Pagination.test.tsx`
  - `src/components/ui/__tests__/FileFiltersBar.test.tsx`
  - `src/components/ui/__tests__/AllFilesModal.test.tsx`
  - `src/components/files/__tests__/FileListItem.test.tsx`
  - `src/components/onboarding/__tests__/AssetUploadForm.test.tsx`
- [x] 7.4 E2E tests - `e2e/file-browser.spec.ts` + `playwright.config.ts`

### Phase 8: Deployment ⏳ READY
- [x] 8.1 Environment variables documented
- [x] 8.2 GCS permissions verified
- [x] 8.3 Docker deployment commands documented
- [x] 8.4 Railway deployment commands documented
- [x] 8.5 Rollback plan documented
- [x] 8.6 Pre-deployment checklist created
- [ ] 8.7 Local Docker deployment - Run `docker compose build && docker compose up -d`
- [ ] 8.8 Smoke testing - Run verification commands
- [ ] 8.9 Railway production deployment - Push to main branch
- [ ] 8.10 Post-deployment verification - Check all endpoints
