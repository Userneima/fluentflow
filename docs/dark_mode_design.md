# FluentFlow Dark Mode Design Rules

Reference implementation: snapvee.com. All values are hardcoded Tailwind classes, not Material Design tokens.

## Surface Elevation

Dark mode communicates depth through luminance (lighter = closer), not shadows. Every element with a light-mode box-shadow must add `dark:shadow-none`.

| Role | Light | Dark |
|------|-------|------|
| Page background | `bg-[#f8f7fb]` / `bg-surface` | `dark:bg-[#101010]` |
| Sidebar | `bg-[#fbfbfb]` | `dark:bg-[#0a0a0a]` |
| Card / raised surface | `bg-white border border-[#dedada]` | `dark:bg-white/[0.06] dark:border-white/[0.12] dark:shadow-none` |
| Elevated card (nested) | `bg-[#f4f3f3]` | `dark:bg-white/[0.08]` |
| Hover state (on surface) | `hover:bg-[#efeeee]` | `dark:hover:bg-white/[0.08]` |
| Popover / menu | `bg-white border border-[#e5e5e5]` | `dark:bg-[#101010] dark:border-white/[0.12]` |
| Input / textarea | `bg-[#fbfbfb] border border-[#dedada]` | `dark:bg-white/[0.06] dark:border-white/[0.12]` |
| Tab / chip bar container | `bg-[#f4f3f3] border border-[#dedada]` | `dark:bg-white/[0.08] dark:border-white/[0.12]` |
| Active tab / segment | `bg-white shadow-sm` | `dark:bg-white/[0.16]` |

## Text Hierarchy

Use white + opacity to create hierarchy on dark surfaces.

| Role | Class | Usage |
|------|-------|-------|
| Primary | `dark:text-white` | Headings, body text, active nav item |
| Primary muted | `dark:text-white/[0.92]` | Wrapper-level default text |
| Secondary | `dark:text-white/[0.72]` | Inactive nav links |
| Muted | `dark:text-white/55` | Labels, descriptions, meta, timestamps |
| Disabled / placeholder | `dark:text-white/30-40` | Input placeholders, empty states |

## Borders

- Visible surfaces: `dark:border-white/[0.12]`
- Dashed / dropzone: `dark:border-white/[0.16]`
- Dropzone hover: `dark:hover:border-white/[0.4]`
- Divider lines: `dark:border-white/[0.12]`

## Interactive Elements

### Filled buttons (dark background in light mode)
Invert to light background in dark mode:
- `bg-[#111111] text-white hover:bg-[#2a2a2a]` → `dark:bg-white dark:text-[#111111] dark:hover:bg-[#e8e8e8]`

### Outline / secondary buttons
- `border border-[#dedada] bg-white text-[#111111] hover:bg-[#f4f3f3]` → `dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:hover:bg-white/[0.12]`

### Progress bar
- Track: `bg-[#efeeee]` → `dark:bg-white/[0.12]`
- Fill: `bg-[#111111]` → `dark:bg-white`

### Tab / segment toggle (inactive)
- `text-[#777] hover:text-[#111111]` → `dark:text-white/55 dark:hover:text-white`

## Alerts

### Error
- `border border-red-200 bg-red-50 text-red-700` → `dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-300`
- Cancel button: add `dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-300 dark:hover:bg-red-400/20`

### Success
- `border border-emerald-200 bg-emerald-50 text-emerald-800` → `dark:border-emerald-400/30 dark:bg-emerald-400/10 dark:text-emerald-300`

## Status Badges

- Light: `bg-white text-[#666]` on a tinted card
- Dark: `dark:bg-white/[0.16] dark:text-white/70`

## Sidebar Specific

- Shell: `bg-[#fbfbfb] text-[#111111] border-r border-[#e5e5e5]` → `dark:bg-[#0a0a0a] dark:text-white/[0.92] dark:border-white/[0.12]`
- Nav item active: `bg-[#e8e5e5] text-[#111111]` → `dark:bg-white/[0.12] dark:text-white`
- Nav item inactive: `text-[#111111] hover:bg-[#efeeee]` → `dark:text-white/[0.72] dark:hover:bg-white/[0.08] dark:hover:text-white`
- Collapse button: `text-[#5f6368] hover:bg-[#efeeee] hover:text-[#111111]` → `dark:text-white/70 dark:hover:bg-white/[0.08] dark:hover:text-white`
- Bottom section border: `dark:border-white/[0.12]`
- Account button: `dark:border-white/[0.12] dark:bg-white/[0.06] dark:hover:border-white/[0.18] dark:hover:bg-white/[0.09]`
- Avatar circle: `bg-[#efeeee] text-[#111111]` → `dark:bg-white/[0.12] dark:text-white`
- Popover: `dark:bg-[#101010] dark:border-white/[0.12]`
- Popover menu item: `dark:text-white dark:hover:bg-white/[0.08]`
- Popover icon: `dark:text-white/70`
- Popover separator: `dark:border-white/[0.12]`

## Material Design Tokens (primary / tertiary)

`tailwind.config.cjs` maps `primary`, `tertiary`, and their container/on- variants to CSS variables defined in `frontend/index.html`. These switch between light and dark values via the `.dark` class. Tokens are no longer hardcoded — `text-primary`, `bg-primary/10`, `border-primary/20`, `text-tertiary`, `bg-tertiary/5`, etc. all adapt to dark mode automatically.

## Missing Global CSS Override

`border-amber-400/25` — used in processing.jsx warnings. Not covered by the existing `!important` override list (only `border-amber-200/50` and `border-amber-200/60` are overridden). Add to dark overrides.

## Audit Checklist

When adding or modifying a page, verify in dark mode:

1. No box-shadow survives without `dark:shadow-none`
2. Every card / raised surface has `dark:bg-white/[0.06] dark:border-white/[0.12]`
3. Text uses correct opacity tier (primary / 0.72 / 0.55)
4. Filled dark buttons invert to `dark:bg-white dark:text-[#111111]`
5. Inputs and textareas have visible borders and distinct background
6. Alerts use the translucent red/green pattern
7. No element is invisible or unreadable due to missing contrast
