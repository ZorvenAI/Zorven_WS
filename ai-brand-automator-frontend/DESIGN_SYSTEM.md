# AI Brand Automator Design System

## "Digital Twilight" Color Palette

A sophisticated, futuristic palette designed for AI-powered brand building.

### Color Tokens

| Token | Hex | Usage |
|-------|-----|-------|
| `brand-midnight` | `#0A0B10` | Deep background, primary dark surface |
| `brand-electric` | `#fad55c` | Primary CTAs, AI spark, interactive elements |
| `brand-ghost` | `#8A2BE2` | Accent, secondary gradients, hover states |
| `brand-silver` | `#E1E1E6` | Primary text, body content |
| `brand-mint` | `#39FF14` | Success states, automated/active indicators |

### Typography

| Token | Font | Usage |
|-------|------|-------|
| `font-heading` | Space Grotesk | Headlines, titles, feature text |
| `font-body` | Inter | Body text, paragraphs, UI labels |
| `font-mono` | JetBrains Mono | Code, technical data, metrics |

### Background Effects

| Token | Description |
|-------|-------------|
| `bg-aura-glow` | Radial purple glow centered, for hero sections |
| `bg-glass-gradient` | Subtle glass morphism gradient for cards |

### Component Classes

#### `.glass-card`
Glass morphism card with blur, subtle border, and shadow.
```css
@apply bg-glass-gradient backdrop-blur-md border border-white/10 rounded-2xl;
```

#### `.btn-primary`
Pista green button with glow hover effect.
```css
@apply bg-brand-electric text-brand-midnight font-bold px-6 py-3 rounded-lg;
```

#### `.ai-pulse`
Adds a subtle pulsing overlay for AI-processing states.

### Usage Guidelines for Copilot

1. **Backgrounds**: Use `brand-midnight` for main backgrounds, `brand-ghost/10` for subtle overlays
2. **Text**: Use `brand-silver` for body, `white` for headings, `brand-silver/70` for secondary
3. **Interactive**: Use `brand-electric` for primary actions, `brand-ghost` for secondary
4. **Success/Active**: Use `brand-mint` for success states and active automation indicators
5. **Cards**: Always use `.glass-card` class for dashboard widgets and content containers
6. **Buttons**: Use `.btn-primary` for main CTAs

### Example Component Pattern

```tsx
<div className="glass-card p-6 ai-pulse group hover:border-brand-electric/50 transition-colors">
  <div className="flex items-center gap-4 mb-4">
    <div className="text-brand-electric">{icon}</div>
    <h3 className="text-xl font-heading">{title}</h3>
  </div>
  <p className="text-brand-silver/70 leading-relaxed font-body">
    {description}
  </p>
</div>
```
