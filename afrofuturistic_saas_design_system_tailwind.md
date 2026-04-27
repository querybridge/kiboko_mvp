# Afro-Futuristic Enterprise SaaS Design System

## Product Direction

This design system is for a dark-first, dashboard-heavy internal SaaS app for ecommerce teams. The visual direction is afro-futuristic in spirit: precise geometry, high contrast, layered surfaces, advanced controls, and quiet energy. It should feel inspired by a futuristic technical lab without referencing or copying any specific franchise, character, setting, or protected design.

The app should feel:

- Corporate-friendly
- Fast and data-dense
- Premium but restrained
- Internal-operations ready
- Dashboard-first
- Flat, not glossy or cinematic

Avoid IP-specific references, shapes, symbols, language, or ornamentation from any entertainment property.

---

## Design Rule: 60 / 30 / 10

Every screen should follow this visual balance:

- **60% dominant neutral**: backgrounds, surfaces, tables, panels, cards
- **30% secondary brand color**: navigation, section framing, active zones, selected states
- **10% accent color**: CTAs, alerts, active metrics, chart emphasis, focus states

This keeps the app professional while still giving it a distinct identity.

---

## Color Tokens

### Raw Palette

```css
--color-brand-purple: #5C3C9F;
--color-brand-teal: #69D6D6;
--color-brand-navy: #1F2C93;
--color-brand-violet: #6E55E0;
--color-brand-blue: #65AFFF;
```

### Semantic Tokens

```css
--bg-app: #0B1020;
--bg-surface: #111827;
--bg-surface-muted: #172033;
--bg-elevated: #1E293B;

--border-subtle: #263248;
--border-strong: #334155;

--text-primary: #F8FAFC;
--text-secondary: #CBD5E1;
--text-muted: #94A3B8;
--text-disabled: #64748B;

--brand-primary: #1F2C93;
--brand-secondary: #5C3C9F;
--brand-tertiary: #6E55E0;

--accent-primary: #69D6D6;
--accent-secondary: #65AFFF;

--success: #22C55E;
--warning: #F59E0B;
--danger: #EF4444;
--info: #65AFFF;
```

### Usage Guidance

| Token | Use |
|---|---|
| `bg-app` | Main app background |
| `bg-surface` | Cards, tables, side panels |
| `bg-elevated` | Modals, dropdowns, overlays |
| `brand-primary` | Main nav, persistent UI structures |
| `brand-secondary` | Secondary navigation, selected sections |
| `accent-primary` | Primary actions and important active states |
| `accent-secondary` | Secondary actions and data highlights |

---

## Typography

### Recommended Fonts

Use:

- **Inter** for body, dashboards, tables, forms, and controls
- **Space Grotesk** for page titles, section headers, and high-level dashboard labels

### Font Loading

Use Google Fonts or self-hosted font files.

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
```

### Type Scale

| Style | Size | Weight | Use |
|---|---:|---:|---|
| Display | 36px | 700 | Rare executive summary pages |
| H1 | 30px | 700 | Page title |
| H2 | 24px | 600 | Dashboard sections |
| H3 | 20px | 600 | Card groups |
| Body | 14px | 400/500 | Default UI text |
| Small | 12px | 500 | Labels, captions, table metadata |

---

## Logo Assets

Place logo assets in the local project directory:

```txt
/Users/querybridge/envs/kiboko_itg/kiboko-app/kiboko-frontend/src/assets/icons/kibokoLogo.svg
/Users/querybridge/envs/kiboko_itg/kiboko-app/kiboko-frontend/public/c.ico
```

Logo rules:

- Use inverse logo on dark backgrounds
- Keep logo flat with no effects
- Do not recolor the logo dynamically unless using approved SVG variants
- Minimum height: 24px
- Clear space: equal to the logo mark height

---

## Tailwind Config

Create or update `tailwind.config.js`:

```js
/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
    './templates/**/*.html',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['Space Grotesk', 'Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        app: {
          bg: '#0B1020',
          surface: '#111827',
          muted: '#172033',
          elevated: '#1E293B',
        },
        brand: {
          purple: '#5C3C9F',
          teal: '#69D6D6',
          navy: '#1F2C93',
          violet: '#6E55E0',
          blue: '#65AFFF',
        },
        ink: {
          primary: '#F8FAFC',
          secondary: '#CBD5E1',
          muted: '#94A3B8',
          disabled: '#64748B',
        },
        line: {
          subtle: '#263248',
          strong: '#334155',
        },
        status: {
          success: '#22C55E',
          warning: '#F59E0B',
          danger: '#EF4444',
          info: '#65AFFF',
        },
      },
      borderRadius: {
        app: '12px',
        card: '16px',
        panel: '20px',
      },
      boxShadow: {
        card: '0 12px 30px rgba(0, 0, 0, 0.22)',
        panel: '0 20px 50px rgba(0, 0, 0, 0.28)',
      },
      spacing: {
        18: '4.5rem',
        22: '5.5rem',
      },
    },
  },
  plugins: [],
};
```

---

## Base CSS

Create `src/styles/design-system.css` or add this to the main CSS file:

```css
:root {
  color-scheme: dark;
}

html {
  background: #0B1020;
}

body {
  margin: 0;
  font-family: Inter, system-ui, sans-serif;
  background: #0B1020;
  color: #F8FAFC;
}

* {
  box-sizing: border-box;
}

::selection {
  background: #69D6D6;
  color: #0B1020;
}

.focus-ring {
  outline: 2px solid #69D6D6;
  outline-offset: 2px;
}
```

---

## Component Patterns

### App Shell

Use a dark neutral app background with a persistent left nav.

Recommended structure:

```txt
AppShell
├── Sidebar
├── Topbar
└── MainContent
    ├── PageHeader
    ├── KPI Row
    ├── Filters
    ├── Charts
    └── Data Tables
```

### Sidebar

Use `brand-navy` or `app-surface`.

```html
<aside class="w-64 bg-app-surface border-r border-line-subtle">
```

Active nav item:

```html
<a class="bg-brand-navy text-ink-primary border-l-4 border-brand-teal">
```

### Cards

```html
<section class="rounded-card bg-app-surface border border-line-subtle shadow-card p-5">
```

### KPI Cards

Use compact cards with strong numeric hierarchy.

```html
<div class="rounded-card bg-app-surface border border-line-subtle p-5">
  <p class="text-xs font-medium uppercase tracking-wide text-ink-muted">Revenue</p>
  <p class="mt-2 font-display text-3xl font-semibold text-ink-primary">$1.2M</p>
  <p class="mt-1 text-sm text-status-success">+8.4% vs prior period</p>
</div>
```

### Buttons

Primary:

```html
<button class="rounded-app bg-brand-teal px-4 py-2 text-sm font-semibold text-slate-950 hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-brand-teal focus:ring-offset-2 focus:ring-offset-app-bg">
  Apply Filters
</button>
```

Secondary:

```html
<button class="rounded-app border border-line-strong bg-transparent px-4 py-2 text-sm font-semibold text-ink-secondary hover:bg-app-muted">
  Export
</button>
```

### Tables

Tables should be dense, readable, and low-noise.

```html
<table class="w-full text-sm">
  <thead class="bg-app-muted text-xs uppercase tracking-wide text-ink-muted">
  <tbody class="divide-y divide-line-subtle">
```

Table guidance:

- Right-align currency and percentages
- Left-align names and labels
- Use muted text for metadata
- Keep row height between 44px and 52px
- Use accent colors only for meaningful deltas or alerts

---

## Chart Colors

Use this order for dashboard charts:

```js
export const chartColors = {
  primary: '#69D6D6',
  secondary: '#65AFFF',
  tertiary: '#6E55E0',
  quaternary: '#5C3C9F',
  muted: '#334155',
  success: '#22C55E',
  warning: '#F59E0B',
  danger: '#EF4444',
};
```

Chart rules:

- Use no more than 4 main colors in one chart
- Use teal for the primary metric
- Use blue/violet for comparison series
- Use red, yellow, green only for status meaning
- Avoid decorative gradients
- Keep labels readable on dark backgrounds

---

## Motion

Flat corporate does not mean static. Use restrained motion:

- Hover transitions: 150ms
- Panel transitions: 200ms
- Page transitions: 250ms max
- No bouncing
- No cinematic glows
- No constant motion

Tailwind example:

```html
<div class="transition duration-150 ease-in-out hover:bg-app-muted">
```

---

## Accessibility Rules

- Minimum contrast: WCAG AA
- Every interactive element needs a visible focus state
- Do not use color alone to communicate status
- Include icon + label for warnings and errors
- Tables need accessible column headers
- Forms need labels, not placeholder-only fields

---

## Implementation Instructions for Claude Code

Use this prompt with Claude Code:

```txt
You are helping build a dark-first internal ecommerce SaaS dashboard using Tailwind CSS.

Implement the design system from `afrofuturistic_saas_design_system_tailwind.md`.

Requirements:
1. Use Tailwind CSS with the provided `tailwind.config.js` tokens.
2. Use Inter as the primary UI font and Space Grotesk for headings.
3. Build reusable components for:
   - AppShell
   - Sidebar
   - Topbar
   - PageHeader
   - KPI Card
   - Dashboard Card
   - Filter Bar
   - Data Table
   - Primary Button
   - Secondary Button
   - Status Badge
4. Keep the design dark-first and dashboard-heavy.
5. Use the 60/30/10 color rule:
   - 60% neutral dark surfaces
   - 30% navy/purple structural brand colors
   - 10% teal/blue accent colors
6. Keep the visual style flat, corporate, and enterprise-friendly.
7. Use afro-futuristic inspiration only through geometry, contrast, precision spacing, and advanced dashboard patterns.
8. Do not copy or reference any protected entertainment IP, symbols, terminology, characters, or visual assets.
9. Place logo files at:
   - `/public/assets/logo/logo.svg`
   - `/public/assets/logo/logo-mark.svg`
   - `/public/assets/logo/logo-inverse.svg`
10. Create sample dashboard screens for ecommerce performance, including:
   - Revenue
   - Spend
   - MTS
   - ROAS
   - Conversion Rate
   - AOV
   - Orders
   - Brand performance table
   - Channel performance chart
11. Prioritize clarity, density, and executive readability over decoration.

Before changing files, inspect the project structure and identify whether this is React, Next.js, Vite, Django templates, or another framework. Then implement in the correct locations.
```

---

## Suggested File Structure

For React / Vite / Next.js:

```txt
src/
  components/
    layout/
      AppShell.tsx
      Sidebar.tsx
      Topbar.tsx
      PageHeader.tsx
    ui/
      Button.tsx
      Card.tsx
      Badge.tsx
      FilterBar.tsx
      DataTable.tsx
      KpiCard.tsx
    charts/
      chartColors.ts
  styles/
    design-system.css
public/
  assets/
    logo/
      logo.svg
      logo-mark.svg
      logo-inverse.svg
```

For Django:

```txt
static/
  css/
    design-system.css
  img/
    logo/
      logo.svg
      logo-mark.svg
      logo-inverse.svg
  js/
templates/
  base.html
  components/
    sidebar.html
    topbar.html
    kpi_card.html
    dashboard_card.html
    data_table.html
```

---

## Do Not Do

- Do not use heavy gradients
- Do not use glowing borders everywhere
- Do not use entertainment IP references
- Do not use decorative patterns that compete with data
- Do not overuse teal
- Do not make dashboards feel like marketing landing pages
- Do not sacrifice table readability for style

---

## Definition of Done

A first implementation is complete when:

- Tailwind tokens are installed and working
- Fonts are loaded
- Dark app shell is implemented
- Sidebar and topbar are styled
- KPI cards are reusable
- Dashboard cards are reusable
- Data tables are readable
- Buttons and badges use semantic styling
- Logo paths are ready for local assets
- Sample ecommerce dashboard screen exists
- The UI follows the 60/30/10 rule
