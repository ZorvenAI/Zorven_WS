# Implementation Plan: Onboarding Home Toggle Tabs — Setup Meeting / Prepare in Chat / Go to Forms (OIA-UI-01)

**Status:** Approved <!-- Draft | Pending Review | Approved | Rejected -->
**Date:** 2026-11-03
**Target Environment:** Frontend only — no backend changes, no new GCP resources

Development on this story may not begin until Status = Approved.

---

## 1. User Story

**As an** Admin or Editor using the Onboarding page,
**I want** a three-button toggle group (Setup Meeting, Prepare in Chat, Go to Onboarding Forms) that controls what appears in the main content area,
**so that** I can schedule meetings, prepare for an interview via AI chat, or go straight to the manual wizard — all from a single interface without page navigation.

### What exists today (verified 2026-11-03 against `development_main` @ `81be058c`)

| Element | Code | Behaviour |
|---|---|---|
| "Prepare in chat" button | `OnboardingHome.tsx:129` | `<Link href="/chat">` — navigates away to `/chat` page |
| "Go to onboarding forms" button | `OnboardingHome.tsx:134` | `<Link href={wizardDeepLink(sessions[0])}>` — navigates away to wizard step |
| CalendarPane | `OnboardingHome.tsx:239` | Always rendered in right column (`lg:col-span-1` inside a 3-column grid) |
| ChatInterface | `components/chat/ChatInterface.tsx` (793 lines) | Full AI chat: sidebar, sessions, messages, file upload, pipeline polling, brand context, input history. Only used at `/chat` route. |
| Sessions list | `OnboardingHome.tsx:146–204` | Left column, always visible |
| Recordings list | `OnboardingHome.tsx:206–236` | Left column, always visible |

**Problem:** "Prepare in chat" navigates away to `/chat`, losing the onboarding context. The calendar is always visible even when the user is focused on chat prep. There is no way to toggle between the two activities without leaving the page.

### Acceptance Criteria

- **AC-1 — Three toggle buttons.** The header area shows three buttons: "Setup Meeting" (default selected), "Prepare in Chat", "Go to Onboarding Forms". Styled as a segmented control / toggle group consistent with the CalendarPane's month/week toggle pattern.
- **AC-2 — Setup Meeting is default.** On page load, "Setup Meeting" is selected and the CalendarPane is shown in the content area below the sessions/recordings lists.
- **AC-3 — Prepare in Chat shows inline ChatInterface.** Selecting "Prepare in Chat" renders the full ChatInterface component in place of the CalendarPane. It starts a new session and has all features: sidebar, file upload/drag-drop, pipeline dispatch, brand context selector, message history, input history.
- **AC-4 — Toggle swaps content.** Selecting "Setup Meeting" shows CalendarPane, selecting "Prepare in Chat" shows ChatInterface. They replace each other — only one is visible at a time. Sessions list and recordings list remain visible above regardless of toggle state.
- **AC-5 — Go to Onboarding Forms navigates.** The third button behaves as before — navigates to `wizardDeepLink(sessions[0])` (or `/onboarding/step-1` if no sessions). This is a navigation, not a toggle.
- **AC-6 — Chat state preserved during toggle.** If the user switches from Chat to Calendar and back, the chat session, messages, and scroll position are preserved (component stays mounted but hidden, or state is lifted).
- **AC-7 — Viewer sees read-only.** Per existing AC-3 pattern: viewers see the toggle but "Prepare in Chat" and "Go to Onboarding Forms" are absent (not disabled) for viewers. Viewers see only "Setup Meeting" with read-only calendar.
- **AC-8 — Layout change.** The current 3-column grid (2 cols sessions + 1 col calendar) becomes a full-width layout: sessions/recordings at the top, toggle buttons below, then the toggled content area spanning full width.
- **AC-9 — Existing tests pass.** No regression in `OnboardingHome.test.tsx` or `CalendarPane.test.tsx` (mocks updated as needed for the new structure).
- **AC-10 — New tests cover toggle behaviour.** Unit tests verify: default tab is Setup Meeting, clicking Prepare in Chat shows chat, clicking Setup Meeting shows calendar, Go to Forms navigates, viewer cannot see chat/forms buttons.

---

## 2. Assumptions

1. **No backend changes.** The ChatInterface component communicates with the existing `/ai/chat-sessions/` API. No new endpoints needed.
2. **Separate chat session namespace.** The embedded chat uses the same session storage (`localStorage`) keys as `/chat`. If the user has an active session on `/chat`, switching to onboarding chat will show the same session. This is acceptable — the AI chat is the same tool regardless of where it's accessed. **Needs confirmation — decision Q-1.**
3. **No new dependencies.** The ChatInterface already exists as a self-contained component. No new npm packages required.
4. **ChatInterface is embeddable.** The component reads from `useSearchParams` (line 14) for initial message param. When embedded in onboarding, this still works (the onboarding route has no conflicting search params). The `h-[calc(100vh-3.5rem)]` height constraint is on the `/chat` page wrapper, not on ChatInterface itself — ChatInterface uses `h-full` internally, so it will fill whatever container it's given.
5. **Mobile responsive.** On mobile (`< lg`), the layout is already single-column. The toggle buttons stack or scroll horizontally. ChatInterface's sidebar hides on mobile (existing `hidden md:flex` class).

---

## 3. Tech Stack

- Frontend: Next.js 15 + React 19 + TypeScript strict, `apiClient` only, `lucide-react` icons, "Digital Twilight" design tokens.
- No backend changes. No microservice changes. No deployment changes.

---

## 4. Architecture & Design

### 4.1 Component hierarchy (after)

```
OnboardingPage (/onboarding/page.tsx)
└── OnboardingHome
    ├── <header> — title, description
    ├── SessionsList (existing, always visible)
    ├── RecordingsList (existing, always visible)
    ├── OnboardingTabBar (NEW)
    │   ├── [Setup Meeting]  ← toggle, default selected
    │   ├── [Prepare in Chat] ← toggle (editors only)
    │   └── [Go to Onboarding Forms] ← navigation link (editors only)
    └── <tab content area>
        ├── CalendarPane (visible when tab = "meeting")
        └── ChatInterface (visible when tab = "chat", hidden not unmounted)
```

### 4.2 Toggle state management

```typescript
type OnboardingTab = 'meeting' | 'chat';
const [activeTab, setActiveTab] = useState<OnboardingTab>('meeting');
```

- **CalendarPane**: rendered when `activeTab === 'meeting'`.
- **ChatInterface**: rendered with `display: none` when `activeTab !== 'chat'` to preserve state (AC-6). Mounting ChatInterface lazily on first selection to avoid unnecessary API calls on page load.

```tsx
const [chatMounted, setChatMounted] = useState(false);

// Mount chat on first selection, then keep it alive
useEffect(() => {
  if (activeTab === 'chat') setChatMounted(true);
}, [activeTab]);
```

```tsx
{activeTab === 'meeting' && <CalendarPane />}
{chatMounted && (
  <div className={activeTab === 'chat' ? '' : 'hidden'}>
    <div className="h-[calc(100vh-22rem)]">
      <ChatInterface />
    </div>
  </div>
)}
```

### 4.3 Layout restructure

**Before (3-column grid):**
```
┌──────────────────────┬──────────┐
│  Sessions            │ Calendar │
│  Recordings          │          │
└──────────────────────┴──────────┘
```

**After (full-width stacked):**
```
┌────────────────── Header ──────────────────┐
├────────────────── Sessions ────────────────┤
├────────────────── Recordings ──────────────┤
├── [Setup Meeting] [Prepare in Chat] [Go→] ─┤
├────────────────── Tab Content ─────────────┤
│  (CalendarPane OR ChatInterface)           │
└────────────────────────────────────────────┘
```

### 4.4 OnboardingTabBar design

Matches the existing CalendarPane month/week toggle pattern (`rounded-lg border-white/10 p-0.5` segmented control):

```tsx
<div className="flex items-center gap-2">
  <div className="flex rounded-lg border border-white/10 p-0.5">
    <button
      onClick={() => setActiveTab('meeting')}
      aria-pressed={activeTab === 'meeting'}
      className={`rounded px-3 py-1.5 text-sm font-medium transition-colors ${
        activeTab === 'meeting' ? 'bg-white/10 text-white' : 'text-brand-silver hover:text-white'
      }`}
    >
      <CalendarDays className="mr-1.5 inline h-4 w-4" />
      Setup Meeting
    </button>
    {canEdit && (
      <button
        onClick={() => setActiveTab('chat')}
        aria-pressed={activeTab === 'chat'}
        className={`rounded px-3 py-1.5 text-sm font-medium transition-colors ${
          activeTab === 'chat' ? 'bg-white/10 text-white' : 'text-brand-silver hover:text-white'
        }`}
      >
        <MessageSquare className="mr-1.5 inline h-4 w-4" />
        Prepare in Chat
      </button>
    )}
  </div>
  {canEdit && (
    <Link
      href={wizardDeepLink(sessions[0])}
      className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-brand-silver hover:bg-white/5"
    >
      <FileText className="h-4 w-4" />
      Go to Onboarding Forms
    </Link>
  )}
</div>
```

### 4.5 Files changed

| File | Change | Scope |
|---|---|---|
| `src/components/onboarding/OnboardingHome.tsx` | Replace header buttons with tab bar, replace 3-column grid with stacked layout, add toggle state, lazy-mount ChatInterface | ~120 lines changed |
| `src/components/onboarding/__tests__/OnboardingHome.test.tsx` | Update mocks (add ChatInterface mock), add toggle-behaviour tests | ~80 lines added |
| No new files | Tab bar is simple enough to inline in OnboardingHome; no need for a separate component | — |

### 4.6 Files NOT changed

| File | Reason |
|---|---|
| `ChatInterface.tsx` | Used as-is — no modifications needed. It's already a self-contained component that accepts `h-full` from its container. |
| `CalendarPane.tsx` | Used as-is — no modifications needed. |
| `/app/chat/page.tsx` | Untouched — the `/chat` route continues to work independently. |
| `/app/onboarding/page.tsx` | Untouched — still renders `<OnboardingHome />`. |
| Any backend file | No backend changes. |

---

## 5. Implementation Steps

### Step 1: Restructure OnboardingHome layout (sessions + recordings full-width)

Remove the `lg:grid-cols-3` grid wrapper. Move sessions and recordings into a full-width stacked layout. Remove the `<CalendarPane />` from the right column (it moves to the tab content area in Step 2).

Remove the header's "Prepare in chat" `<Link>` and "Go to onboarding forms" `<Link>` — they are replaced by the tab bar.

**Touches:** `OnboardingHome.tsx`

### Step 2: Add tab state and tab bar

Add `activeTab` state (`'meeting' | 'chat'`, default `'meeting'`). Add `chatMounted` state for lazy mounting. Render the segmented-control tab bar between the recordings section and the content area. "Go to Onboarding Forms" remains a `<Link>` beside the toggle group.

Render `<CalendarPane />` when `activeTab === 'meeting'`. Viewers see only the Setup Meeting button (AC-7).

**Touches:** `OnboardingHome.tsx`

### Step 3: Embed ChatInterface in the chat tab

Import `ChatInterface` from `@/components/chat/ChatInterface`. Wrap in a `Suspense` boundary (matching `/chat/page.tsx`). Lazy-mount on first tab selection. Hide with `className="hidden"` when not active (preserving session state per AC-6). Set a fixed height container so the chat fills the available space.

**Touches:** `OnboardingHome.tsx`

### Step 4: Remove the "Prepare your first meeting in chat" link

The empty-state section (line 165–172) currently links to `/chat`. Replace with a button that sets `activeTab = 'chat'` so the user stays on the page.

**Touches:** `OnboardingHome.tsx`

### Step 5: Update tests

1. Mock `ChatInterface` (same pattern as CalendarPane mock in existing tests).
2. Update editor-affordance tests: verify three elements exist — Setup Meeting button, Prepare in Chat button, Go to Onboarding Forms link.
3. Add toggle tests: click "Prepare in Chat" → chat region visible, calendar region hidden. Click "Setup Meeting" → calendar visible, chat hidden.
4. Verify viewer tests: "Prepare in Chat" and "Go to Onboarding Forms" absent.
5. Verify default state: Setup Meeting is pressed, CalendarPane is rendered.

**Touches:** `OnboardingHome.test.tsx`

---

## 6. Testing

### 6.1 Unit tests

| Test | Asserts |
|---|---|
| `renders Setup Meeting tab as default` | `aria-pressed="true"` on Setup Meeting button, CalendarPane mock visible |
| `renders Prepare in Chat tab for editors` | Button present when `canEdit = true` |
| `hides Prepare in Chat and Go to Forms for viewers` | Buttons absent (not disabled) when `canEdit = false` |
| `clicking Prepare in Chat shows chat and hides calendar` | After click: chat container visible, calendar mock absent |
| `clicking Setup Meeting after chat shows calendar` | After toggling back: calendar mock visible, chat container hidden |
| `Go to Onboarding Forms is a navigation link` | `<a>` element with correct `href` |
| `empty-state link switches to chat tab` | Clicking the empty-state "Prepare in chat" sets `activeTab` to `chat` |

### 6.2 Property tests

Not applicable — this is a UI layout change with discrete states, not a data transformation.

### 6.3 Integration tests

Not applicable — no backend changes, no new API calls. ChatInterface's own integration with the backend is already tested in `ChatInterface.test.tsx`.

### 6.4 E2E tests (manual verification)

| Scenario | Steps | Expected |
|---|---|---|
| Default load | Navigate to `/onboarding` | Setup Meeting selected, calendar visible |
| Toggle to chat | Click "Prepare in Chat" | Chat loads, calendar gone. Can type a message and get AI response. |
| Toggle back | Click "Setup Meeting" | Calendar visible. Click "Prepare in Chat" again — chat still has previous messages (state preserved). |
| Go to forms | Click "Go to Onboarding Forms" | Navigates to wizard step. |
| Viewer | Log in as viewer, navigate to `/onboarding` | Only "Setup Meeting" visible. No chat or forms buttons. |
| Mobile | Resize to mobile width | Tab bar is usable, chat sidebar hidden, no horizontal overflow. |

---

## 7. GCP Cost Estimation

**No GCP cost impact.** This is a frontend-only change. No new Cloud Run services, no new API endpoints, no additional Memorystore usage. The ChatInterface reuses the existing `/ai/chat-sessions/` API which is already deployed and costed.

---

## 8. Git Workflow

- **Branch:** `feat/oia-ui-01-onboarding-home-tabs` from `development_main`
- **PR target:** `development_main`
- **Commit convention:** `feat(onboarding):` prefix
- **PR title:** `feat(onboarding): add Setup Meeting / Prepare in Chat toggle tabs to OnboardingHome`

---

## 9. Decisions Needing Confirmation

| ID | Question | Recommendation | Impact if wrong |
|---|---|---|---|
| Q-1 | Should the embedded chat share `localStorage` session keys with `/chat`? | **Yes** — the AI chat is the same tool; sharing avoids orphaned sessions. User opening `/chat` later sees the same conversation. | If no: need separate `localStorage` keys (`onboarding_chat_session` vs `active_chat_session`), minor code change in ChatInterface to accept a `storagePrefix` prop. |
| Q-2 | Should "Go to Onboarding Forms" be inside the segmented toggle or a separate button? | **Separate** — it's a navigation action, not a tab. Mixing navigations with toggles is confusing. It sits beside the toggle group as a distinct button. | Purely visual; easy to change. |
| Q-3 | Should switching away from the chat tab pause any active pipeline polling? | **No** — the chat is hidden but mounted, polling continues naturally. If a pipeline completes while on the calendar tab, the result is there when the user switches back. | Could add unnecessary complexity. |

---

## 10. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| ChatInterface's 793 lines + sub-components increase initial bundle for `/onboarding` | Medium | Lazy mount (Step 3) + `React.lazy()` with `Suspense` ensures the chat chunk only loads when the tab is first selected. |
| ChatInterface relies on `useSearchParams` which requires a `Suspense` boundary | Already handled | `/chat/page.tsx` already wraps it in `Suspense`. We replicate this pattern. |
| localStorage session key collision between `/chat` and onboarding chat | Low (see Q-1) | This is intentional shared state. If product decides against it, a `storagePrefix` prop is a small change. |
