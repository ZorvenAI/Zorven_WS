---
applyTo: "ai-brand-automator-frontend/src/**/*.{ts,tsx}"
---

# Frontend Instructions

## Code Style

- **Language**: TypeScript (strict mode)
- **Linter**: ESLint only — no Prettier
- **Path alias**: `@/* → ./src/*`
- **Components**: Functional only — no class-based React
- **Icons**: Use `lucide-react`, avoid other icon libraries

## Design System ("Digital Twilight")

### Colors (use Tailwind classes)

| Token | Class | Hex |
|-------|-------|-----|
| Midnight | `bg-brand-midnight` | `#0a0f1e` |
| Deep Navy | `bg-brand-deep-navy` | `#111827` |
| Electric Violet | `text-brand-electric` | `#8b5cf6` |
| Silver Dawn | `text-brand-silver` | `#d1d5db` |
| Accent Teal | `text-brand-teal` | `#14b8a6` |
| Coral Accent | `text-brand-coral` | `#f97316` |

### Component Classes

- **Cards**: `glass-card` (translucent glass-morphism)
- **Buttons**: `btn-primary` (electric violet gradient), `btn-outline`
- **Containers**: `bg-brand-midnight` or `bg-brand-deep-navy`
- **Headings**: `font-heading text-brand-silver`
- **Interactive**: `glow-ring` on focus states

### Background Effects

- `gradient-mesh` — animated gradient background for hero sections
- `stars-bg` — particle effect for auth pages

## API Calls

```tsx
// ✅ CORRECT — always use apiClient
import { apiClient } from '@/lib/api';
const data = await apiClient.get('/endpoint/');
await apiClient.post('/endpoint/', body);
await apiClient.upload('/endpoint/', formData);

// ❌ WRONG — never use raw fetch
const res = await fetch('/api/endpoint');
```

## Route Protection

```tsx
// ✅ Every protected page must call useAuth()
'use client';
import { useAuth } from '@/hooks/useAuth';

export default function ProtectedPage() {
  useAuth(); // Redirects to login if no JWT
  return <div>...</div>;
}
```

## Error Handling

- Catch API errors from `apiClient` with proper error types from `@/lib/errors.ts`
- HTTP 409 → `DuplicateFileError` (show replace dialog)
- Always set state to empty/default on error — never leave stale data displayed:
  ```tsx
  try {
    const data = await apiClient.get('/endpoint/');
    setItems(data);
  } catch (error) {
    setItems([]);  // Clear stale data
    console.error('Failed to load:', error);
  }
  ```

## Hydration Safety

Components using `useTenantRole()` or `TenantContext` (which reads from `localStorage`) MUST guard with `hasMounted` before rendering role-dependent JSX. Without this, SSR renders with default values (e.g., `canManageTeam=false`) while the client renders with actual values, causing a hydration mismatch.

```tsx
const [hasMounted, setHasMounted] = useState(false);
useEffect(() => setHasMounted(true), []);

if (!hasMounted) return <LoadingSpinner />;
// ... role-dependent JSX below (canManageTeam, isOwner, etc.)
```

## Next.js Conventions

- Use App Router (`app/` directory)
- Mark interactive pages with `'use client'` directive
- Use `loading.tsx` for loading states
- Use `error.tsx` for error boundaries
- Dynamic routes: `app/[param]/page.tsx`

## TypeScript

- Define API response types in component files or `@/types/`
- Use `interface` for object shapes, `type` for unions/intersections
- Never use `any` — use `unknown` and narrow with type guards
- Export types that are used across components
