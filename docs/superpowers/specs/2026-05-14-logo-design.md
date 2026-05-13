# Logo Design Spec — infobroker.tech

**Date:** 2026-05-14
**Status:** Approved, implementation-ready
**Owner:** Rinehard
**Domain:** infobroker.tech
**Product name:** infobroker — Intelligence Platform

---

## 1. Concept

A **network node** mark paired with a bold sans-serif wordmark. The mark is a central hub with five radiating connections, each terminating in a smaller satellite node. Satellites decrease in size and opacity as visual weight falls off from the centre, reinforcing the "hub of intelligence" metaphor — info-broker as the centre, sources as the satellites.

Colour direction: **violet** (`#a78bfa`) — chosen over the previous cyan (`#38bdf8`) for distinctiveness in the OSINT/intelligence-tooling space, which leans heavily blue/green.

---

## 2. Mark Geometry

The mark lives inside a **64 x 64** SVG viewBox. All coordinates below are absolute.

### 2.1 Central hub

- Centre: `(32, 32)`
- Radius: `10`
- Fill: `var(--brand-violet)` (`#a78bfa`)
- Stroke: none

### 2.2 Satellites (5 nodes)

Satellites sit on a circle of radius `24` around the hub, with angles measured **clockwise from 12 o'clock (top)**. Five satellites, evenly distributed (72 degrees apart), starting at the top.

| # | Angle (deg) | cx     | cy     | r   | opacity |
|---|-------------|--------|--------|-----|---------|
| 1 | 0           | 32.00  | 8.00   | 4.0 | 1.00    |
| 2 | 72          | 54.83  | 24.58  | 3.4 | 0.85    |
| 3 | 144         | 46.11  | 51.41  | 2.8 | 0.70    |
| 4 | 216         | 17.89  | 51.41  | 2.4 | 0.55    |
| 5 | 288         | 9.17   | 24.58  | 3.0 | 0.78    |

Coordinates derived from `cx = 32 + 24 * sin(theta)`, `cy = 32 - 24 * cos(theta)`.

All satellites fill `var(--brand-violet)`; opacity applied at the `<circle>` level (not via colour alpha) so a single colour token drives the mark.

### 2.3 Connecting lines

Five lines from hub centre to each satellite centre. To avoid drawing inside the hub circle and into the satellite circles, lines are drawn from the **hub edge** to the **satellite edge** along the same angle.

For each satellite `i` at angle `theta_i` with radius `r_i`:
- Line start: `(32 + 10 * sin(theta), 32 - 10 * cos(theta))`
- Line end:   `(32 + (24 - r_i) * sin(theta), 32 - (24 - r_i) * cos(theta))`

Computed values:

| # | x1     | y1     | x2     | y2     | opacity |
|---|--------|--------|--------|--------|---------|
| 1 | 32.00  | 22.00  | 32.00  | 12.00  | 0.55    |
| 2 | 41.51  | 28.91  | 51.60  | 25.65  | 0.45    |
| 3 | 37.88  | 40.09  | 44.46  | 44.85  | 0.40    |
| 4 | 26.12  | 40.09  | 19.59  | 44.85  | 0.35    |
| 5 | 22.49  | 28.91  | 12.40  | 25.65  | 0.45    |

Stroke: `var(--brand-violet)`, `stroke-width="1.25"`, `stroke-linecap="round"`.

### 2.4 Render order (canonical)

The implementing agent should emit a `<svg>` root with `viewBox="0 0 64 64"` and the standard SVG namespace attribute, then render children in this z-order (bottom to top):

1. The five `<line>` elements (§2.3, in order 1..5).
2. The five satellite `<circle>` elements (§2.2, in order 1..5).
3. The central hub `<circle>` (§2.1).

Lines render first so satellite circles cleanly cap them; the hub renders last so it sits visually "on top" of any line that would otherwise clip into it.

---

## 3. Typography

### 3.1 Font family

Primary: **Inter** (variable font preferred). Available via the `@fontsource-variable/inter` npm package or by loading weights 500 + 700 from Google Fonts.

- Fallback stack: `"Inter", system-ui, -apple-system, "Segoe UI", sans-serif`.

If Inter is not present, fall back to `Space Grotesk` (only as alternate brand font). Do not mix the two.

### 3.2 Wordmark — "infobroker"

- Weight: **700** (Bold)
- Case: lowercase
- Letter-spacing: `-0.02em` (tight, for confidence)
- Colour: `var(--brand-violet)` on dark and light variants
- Line-height: `1` (single line; no vertical drift)
- Optical alignment: vertical centre of "infobroker" aligns with vertical centre of the mark.

### 3.3 Tagline — "INTELLIGENCE PLATFORM"

- Weight: **500** (Medium)
- Case: UPPERCASE
- Letter-spacing: `0.18em` (wide, for hierarchy contrast)
- Colour: `var(--brand-tagline)` on dark and light
- Position: directly below "infobroker", left-aligned with the "i" of "infobroker"
- Top margin: `0.25 * wordmark-size`

### 3.4 Size ratios (per size token)

| Size | Mark | Wordmark "infobroker" | Tagline | Gap mark to wordmark |
|------|------|------------------------|---------|----------------------|
| sm   | 24px | 14px                   | 8px     | 8px                  |
| md   | 32px | 18px                   | 10px    | 10px                 |
| lg   | 48px | 24px                   | 13px    | 14px                 |

Tagline size approximately `0.55 * wordmark-size`, rounded to nearest pixel.

---

## 4. Colour Tokens

Add to `frontend/src/index.css` under the existing `:root` (and in dark theme if separated):

```css
:root {
  --brand-violet: #a78bfa;
  --brand-violet-dim: rgba(167, 139, 250, 0.6);
  --brand-text-dark: #e2e8f0;
  --brand-text-light: #1e293b;
  --brand-tagline: #64748b;
  --brand-bg-dark: #0b1020;
  --brand-bg-light: #ffffff;
}
```

Notes:
- The wordmark is **violet on both** dark and light variants. `--brand-text-dark` / `--brand-text-light` exist only as fallbacks for monochrome contexts (invoices, contracts) where the violet cannot render.
- Satellite "fade" is achieved by per-circle `opacity`, not a separate colour token. `--brand-violet-dim` is exposed for any non-SVG UI element (hover glow, focus ring) that wants a softened violet.

---

## 5. Variants

### 5.1 Full horizontal lockup

Mark on the left, wordmark + tagline stacked on the right. Used in:
- Login page header
- App top-bar on wide layouts
- Email signatures
- OG image (centred)

### 5.2 Mark only

Square, no wordmark. Used in:
- `IconRail` top item (replaces the current hex glyph)
- Favicon (`favicon.svg`)
- App tab icon
- Loading states / spinners (rotate slowly)

### 5.3 Dark background (primary)

- Background: `#0b1020` or app dark surface
- Mark: violet (`#a78bfa`)
- Wordmark: violet
- Tagline: slate (`#64748b`)

### 5.4 Light background

- Background: `#ffffff`
- Mark: violet (`#a78bfa`) — same
- Wordmark: violet — same
- Tagline: slate (`#64748b`) — same

(No colour inversion is required; the palette is dual-bg safe. Light variant exists as a switch only for the rare monochrome export.)

---

## 6. Component API

### 6.1 `frontend/src/components/brand/LogoMark.tsx`

```typescript
export type LogoMarkProps = {
  /** Pixel size of the square mark. Default: 32. */
  size?: number;
  /** Override the mark colour. Defaults to var(--brand-violet). */
  color?: string;
  /** Optional className passthrough. */
  className?: string;
  /** Optional ARIA label. Default: "infobroker". */
  title?: string;
};

export function LogoMark(props: LogoMarkProps): JSX.Element;
```

Renders the canonical 64x64 viewBox SVG described in §2, scaled via the `size` prop (`width` + `height`). The `color` prop, if provided, replaces every `fill="#a78bfa"` and `stroke="#a78bfa"` with the supplied value.

### 6.2 `frontend/src/components/brand/Logo.tsx`

```typescript
export type LogoSize = "sm" | "md" | "lg";
export type LogoVariant = "dark" | "light";

export type LogoProps = {
  /** Size token. Default: "md". */
  size?: LogoSize;
  /** Background variant the logo will sit on. Default: "dark". */
  variant?: LogoVariant;
  /** If true, render mark only (no wordmark). Default: false. */
  markOnly?: boolean;
  /** Show the "INTELLIGENCE PLATFORM" tagline. Default: true. */
  tagline?: boolean;
  /** Optional className passthrough. */
  className?: string;
};

export function Logo(props: LogoProps): JSX.Element;
```

Layout:
- Outer element: `<div role="img" aria-label="infobroker — Intelligence Platform">`
- Flex row, `align-items: center`, gap from §3.4
- Left: `<LogoMark size={markPx} />`
- Right (skipped if `markOnly`): a `<div>` column with the wordmark `<span>` and (if `tagline`) the tagline `<span>`

Size to pixel mapping is the table in §3.4.

The `variant` prop only changes the tagline / fallback text colour; the mark and wordmark are violet in both. When `variant="light"`, the component MUST NOT assume a background — it only ensures its own text is readable.

### 6.3 `frontend/public/favicon.svg`

Standalone SVG identical in geometry to §2, with these additions:
- Root attribute: `width="32" height="32"`
- No `<style>` blocks, no external font references, no `currentColor` (favicon must render before CSS loads).
- Use the literal `#a78bfa` colour values inline.

### 6.4 `frontend/public/og-image.svg`

- viewBox: `0 0 1200 630`
- Background: solid `#0b1020`
- Centred full lockup at `lg` size, scaled up:
  - Mark: 160px (centred at `(540, 295)`)
  - Wordmark "infobroker": 96px, weight 700, fill `#a78bfa`
  - Tagline "INTELLIGENCE PLATFORM": 28px, weight 500, letter-spacing `0.18em`, fill `#64748b`
- Optional faint grid backdrop using `--brand-violet-dim` at opacity 0.04 — single 60px square pattern. Skip if it complicates rendering.

---

## 7. Usage Rules

| Location                                   | Variant                                       |
|--------------------------------------------|-----------------------------------------------|
| `IconRail` top item                        | `<LogoMark size={20} />`                      |
| Login page header                          | `<Logo size="md" variant="dark" />`           |
| App top-bar (wide)                         | `<Logo size="sm" variant="dark" />`           |
| App top-bar (narrow / mobile)              | `<Logo size="sm" markOnly />`                 |
| Loading screen                             | `<LogoMark size={64} />` (rotated, 4s loop)   |
| Email signature                            | `<Logo size="sm" variant="light" />`          |
| Browser tab / favicon                      | `favicon.svg`                                 |
| Social preview (OG)                        | `og-image.svg`                                |

Clear-space rule: leave at least `0.5 * mark-size` of padding around any logo placement.

Do not:
- Re-colour the mark to anything outside `var(--brand-violet)` (except the documented monochrome fallback).
- Add drop shadows, gradients, or strokes around the wordmark.
- Rotate the wordmark.
- Skew or stretch the mark non-uniformly.

---

## 8. Implementation Tasks

The implementing agent should:

1. **Create `frontend/src/components/brand/` directory.**

2. **Create `LogoMark.tsx`** implementing §6.1, using the geometry from §2.1–§2.3 in the render order specified in §2.4. The `size` prop sets `width`/`height` only; the viewBox stays `0 0 64 64`.

3. **Create `Logo.tsx`** implementing §6.2. Compose `<LogoMark>` + a flex layout for the wordmark/tagline. Use the size table in §3.4.

4. **Add CSS tokens** from §4 to `frontend/src/index.css` (append to the existing `:root` block; do not duplicate any existing keys).

5. **Create `frontend/public/favicon.svg`** per §6.3. Update `frontend/index.html` `<link rel="icon">` to reference `/favicon.svg` (type `image/svg+xml`).

6. **Create `frontend/public/og-image.svg`** per §6.4. Update `<head>` `og:image` / `twitter:image` meta tags to `/og-image.svg`.

7. **Update `frontend/src/components/layout/IconRail.tsx`:** locate the line that renders the hex glyph (`⬡`) as the top home/logo symbol and replace with `<LogoMark size={20} />`. Add the import. Use the path alias `@/components/brand/LogoMark` if `@/` is configured; otherwise use a relative path.

8. **Update `frontend/src/pages/Login.tsx`:** replace any text-only product header (e.g. `<h1>info-broker</h1>` or similar) with:
   ```tsx
   <Logo size="md" variant="dark" />
   ```
   Import path: `@/components/brand/Logo` (or relative equivalent).

9. **Verify Inter is loaded.** If `@fontsource-variable/inter` (or a `<link>` to Google Fonts Inter weights 500 + 700) is not already in the bundle, add it. The wordmark requires weight 700; the tagline requires weight 500.

10. **Test** — render the login page and IconRail in dev. Confirm:
    - Mark is violet `#a78bfa`.
    - Wordmark says exactly "infobroker" (lowercase, no `.tech`).
    - Tagline says exactly "INTELLIGENCE PLATFORM" (uppercase, letter-spaced).
    - Favicon updates in the browser tab.
    - No console warnings about missing fonts.

---

## 9. Acceptance Criteria

- [ ] `LogoMark` renders the exact geometry from §2.1–§2.3 with no deviation in coordinates.
- [ ] `Logo` renders mark + wordmark + tagline in the three documented sizes.
- [ ] `markOnly` prop suppresses the wordmark column entirely (no empty flex child).
- [ ] CSS tokens from §4 exist in `index.css` and are referenced by the components.
- [ ] `favicon.svg` and `og-image.svg` exist in `frontend/public/` and are referenced from `index.html`.
- [ ] `IconRail` shows the mark in place of the hex glyph; no other glyphs in the rail are altered.
- [ ] Login page shows the full lockup at `md` size.
- [ ] No new lint, typecheck, or build errors introduced.

---

## 10. Test Plan

- **Visual:** screenshot login page (dark) and confirm the mark matches the geometry in §2.
- **Unit:** snapshot test `LogoMark` and `Logo` (all sizes × both variants × `markOnly` true/false) in `frontend/src/components/brand/__tests__/`.
- **a11y:** axe-core run on login page; confirm the logo has `role="img"` and a meaningful `aria-label`.
- **Build:** `pnpm build` (or repo's package manager equivalent) succeeds with no missing-asset warnings for `favicon.svg` / `og-image.svg`.
- **E2E:** Playwright assertion that the login page renders `[aria-label*="infobroker"]` and the favicon URL returns 200.
