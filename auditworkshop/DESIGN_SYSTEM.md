# Auditworkshop Design System

## Colors

The application relies heavily on the `slate`, `cyan`, `indigo`, and `emerald` color palettes from Tailwind CSS 4.

### UI Colors
- **Primary:** `indigo-600` (Dark: `indigo-400`)
- **Background (Light):** Custom CSS `var(--app-bg)` (radial-gradient mixing cyan/yellow hints with linear-gradient #f5f7f2 to #f6f3eb)
- **Background (Dark):** Custom CSS `var(--app-bg)` (radial-gradient with slate transparent to #020617 / #0b1120)
- **Cards (Light):** `bg-white/90` or `bg-white` with `border-slate-200`
- **Cards (Dark):** `bg-slate-900/90` or `bg-slate-950/70` with `border-slate-800`

### Semantic / Feedback Colors
- **Success / Accepted:** `emerald-600` (Light) / `emerald-400` (Dark)
- **Warning / Draft:** `amber-600` (Light) / `amber-400` (Dark)
- **Error / Rejected:** `red-600` (Light) / `red-400` (Dark)
- **Info / Edited:** `blue-600` (Light) / `blue-400` (Dark)

## Layout & Spacing

- **Sidebar Width:** 320px (`w-80`)
- **Global Constraints:** Standard max widths `max-w-4xl`, `max-w-6xl`
- **Border Radius:** Very soft and rounded components (`rounded-2xl`, `rounded-[28px]`, `rounded-full`)

## Typography

- **Heading Font:** Fraunces, Iowan Old Style, Palatino Linotype, Georgia, serif
- **Body Font:** IBM Plex Sans, Avenir Next, Segoe UI, Helvetica Neue, sans-serif
- Monospace font is used specifically for Keys (Aktenzeichen, Frage-Keys). 
- Sizes lean heavily towards `text-sm` and `text-xs` for dense auditing density.

## Components & Effects

### Glassmorphism
Premium blurring and semi-transparent cards are used throughout:
```css
/* Typically applied via Tailwind */
.bg-white/75.backdrop-blur-xl
```

### Loading States
We utilize standard Skeleton components with a built-in pulse animation simulating structured data loading (`bg-slate-200/80` or `bg-slate-800/80`).

### Accessibility (A11y)
- Active focus elements use `focus-visible:ring-2 focus-visible:ring-cyan-500` or `focus-visible:ring-indigo-500`.

## Design Tokens

For consistency, the following core token concepts are used conceptually (represented via Tailwind v4 defaults):

```css
/* Core Spacing & Timing */
--sidebar-width: 320px; /* Tailwind: w-80 */
--transition-standard: 200ms ease-in-out;
--transition-slow: 500ms ease-out;

/* Semantic Feedback Tokens */
--color-error-bg: theme('colors.red.50');
--color-error-border: theme('colors.red.200');
--color-error-text: theme('colors.red.700');
/* Dark variants are typically: bg-red-950/30, border-red-800, text-red-400 */

/* Global Shadow */
--shadow-premium: 0 24px 80px -40px rgba(15,23,42,0.5);
```

## Error States

Error messages and API failures are standardized as padded alert blocks:
```tsx
<div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/70 dark:bg-red-950/40 dark:text-red-400">
  {errorMessage}
</div>
```
App-level errors are wrapped in a global `<ErrorBoundary>` matching the premium design.
