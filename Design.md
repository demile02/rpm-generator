---
name: "Atelier Glass"
description: "A studio interface built around real glassmorphism — frosted backdrop-blur cards floating over a soft tonal lavender-bone backdrop. Plus Jakarta Sans for UI, Spectral italic for accent display, a single indigo reserved for the active panel ring and the primary CTA. Built for creative studios, design tools, and product surfaces where the glass IS the interface chrome."
tags: [glass, modern, premium, minimal, saas]
colors:
  primary:   "#1a1830"
  secondary: "#6b6987"
  tertiary:  "#1a1830"
  neutral:   "#e6e3f0"
  surface:   "#eeeaf5"
typography:
  display: Spectral
  body:    "Plus Jakarta Sans"
  mono:    "JetBrains Mono"
  scale:
    hero: "5rem / 1.02 / 500 / -0.035em"
    h1:   "3rem / 1.1 / 600 / -0.025em"
    h2:   "1.625rem / 1.25 / 600 / -0.012em"
    body: "1.0625rem / 1.62 / 400 / -0.005em"
radius:
  sm: 10px
  md: 16px
  lg: 22px
  pill: 9999px
shadows:
  card:   "rgba(26,24,48,0.05) 0 1px 2px, rgba(26,24,48,0.04) 0 8px 24px -8px"
  button: none
borders:
  card:    "1px solid rgba(255,255,255,0.55)"
  divider: rgba(26,24,48,0.10)
buttons:
  primary:
    background: #3d3a8a
    color: #f4f2fb
    border: none
    shape: rounded
    padding: 11px 22px
    font: 600 / 0.875rem
  secondary:
    background: rgba(255,255,255,0.55)
    color: #1a1830
    border: 1px solid rgba(26,24,48,0.10)
    shape: rounded
    padding: 11px 22px
    font: 500 / 0.875rem
  outline:
    background: transparent
    color: #1a1830
    border: 1px solid rgba(26,24,48,0.18)
    shape: rounded
    padding: 11px 22px
    font: 500 / 0.875rem
  ghost:
    background: transparent
    color: #6b6987
    border: none
    shape: rounded
    padding: 11px 16px
    font: 500 / 0.875rem
charts:
  variant: "thin-bars"
  stroke_width: 1.5
  fill_opacity: 0.1
  gridlines: false
  bar_gap: 5px
  highlight: single
  dot_marker: true
fonts_url: "https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Spectral:ital,wght@0,400;0,500;1,400;1,500&family=JetBrains+Mono:wght@400;500&display=swap"
dependencies: ["lucide-react"]
---

# Atelier Glass

## AI Build Instructions

> **Read this section before writing any code.** The rules below
> are non-negotiable. Every value used in the UI must come from this
> file's frontmatter — never substitute, approximate, or invent new
> colors, fonts, radii, or shadows. If a value is missing, ask the
> user before adding one.

### 1 · Your role

You are building UI for a project that has adopted **Atelier Glass** as its
design system. Treat `DESIGN.md` as the single source of truth.
Your job is to translate the user's product requirements into
components and pages that look like they were designed by the same
person who authored this file.

### 2 · Token compliance

- Pull every color, font family, radius, shadow, and spacing value
  from the frontmatter at the top of this file.
- Use semantic roles (e.g. `primary`, `accent`, `muted`) — never
  hard-code hex values that bypass the system.
- When a token can be expressed as a CSS variable, declare it once
  in your global stylesheet and reference it everywhere downstream.
- The Google Fonts `<link>` is provided in the Typography section.
  Add it to `<head>` before any component renders.

### 3 · Component recipes

Use these recipes verbatim when building the corresponding component.

#### Buttons

Four variants are defined. Pick one — never blend variants or invent a fifth.

- **Primary** — rounded shape, bg `#3d3a8a`, text `#f4f2fb`, padding `11px 22px`, weight `600`.
- **Secondary** — rounded shape, bg `rgba(255,255,255,0.55)`, text `#1a1830`, border `1px solid rgba(26,24,48,0.10)`, padding `11px 22px`, weight `500`.
- **Outline** — rounded shape, text `#1a1830`, border `1px solid rgba(26,24,48,0.18)`, padding `11px 22px`, weight `500`.
- **Ghost** — rounded shape, text `#6b6987`, padding `11px 16px`, weight `500`.

Reach for **primary** as the single dominant CTA per screen.
**Secondary** for the supporting action. **Outline** for tertiary
actions in toolbars. **Ghost** for inline links and table actions.

#### Cards

- Background: `#eeeaf5`
- Border: `1px solid rgba(255,255,255,0.55)`
- Shadow: `rgba(26,24,48,0.05) 0 1px 2px, rgba(26,24,48,0.04) 0 8px 24px -8px`
- Radius: `radius.lg` (`22px`)
- Internal padding: `20px` for compact cards, `24–28px` for content cards.

#### Tabs

Variant: `pill`. Segmented control inside a tinted track. Active tab gets a filled pill in the accent color.

#### Charts

- Bar/line variant: `thin-bars`
- No gridlines — let the bars/lines carry the data.
- Highlight strategy: `single` — emphasize a single bar/point per chart.

#### Typography pairings

- **Display (`Spectral`)** — h1, h2, hero headlines, brand wordmarks.
- **Body (`Plus Jakarta Sans`)** — paragraphs, labels, button text, form inputs.
- **Mono (`JetBrains Mono`)** — code, eyebrows, metadata, numerals in tables.

### 4 · Hard constraints

Never do any of the following without explicit instruction from the user:

- Introduce a new color, font, radius, or shadow that isn't declared above.
- Mix this system with another (e.g. don't paste in Material or Bootstrap defaults).
- Use generic gradient defaults (purple→blue, peach→pink) — they break the system's voice.
- Reach for emoji icons. Use a consistent icon library and size icons in line with body type.
- Add motion that exceeds the system's restraint — keep transitions short (≤200ms) and subtle.

### 5 · Before you finish — verify

Run through this checklist for every screen you produce:

- [ ] Every color used appears in the Colors table above.
- [ ] Headlines use the display font; body copy uses the body font.
- [ ] Buttons match one of the declared variants exactly (shape, padding, weight).
- [ ] Border-radius values come from `radius.sm` / `radius.md` / `radius.lg` / `radius.pill`.
- [ ] Cards and dividers use the declared border + shadow tokens.
- [ ] No values were invented; if you needed something missing, you stopped and asked.

---

## 1. Atmosphere

Atelier Glass is a studio interface built around real glassmorphism. The page surface is a soft tonal lavender-bone `#eeeaf5` — never white, never grey. Cards are frosted glass: `background: rgba(255,255,255,0.55)`, `backdrop-filter: blur(20px)`, with a 1px white inner border at 55% opacity that picks up the page tint and reads as light bouncing through the pane. Display headlines run in Spectral 500 at 80px with one italic word per headline — the calligraphic accent through frosted glass. Body sits in Plus Jakarta Sans at 17px on a 1.62 leading. The single accent is deep indigo `#3d3a8a` reserved for the primary CTA, the active panel ring, and the focus state — never as a background, never as a fill.

The discipline is in the glass behaviour: every elevated surface uses `backdrop-filter: blur(20px) saturate(1.4)` with a 55% white tint — the saturation lift is what makes the lavender bleed through and reads as actual frosted glass, not as a grey overlay.

**Signature moves**
- Real `backdrop-filter: blur(20px) saturate(1.4)` on every elevated card
- Lavender-bone surface `#eeeaf5` — the tint that bleeds through the glass IS the system
- Spectral 500 italic accent on one word per headline — the calligraphic moment
- Indigo `#3d3a8a` exclusively on primary CTA + active panel ring + focus state
- 1px inner border at 55% white on every glass card — the bouncing-light edge

## 2. Palette

### Surfaces
- **Lavender Bone** `#eeeaf5` — page background (the tint that bleeds through glass)
- **Lavender Lift** `#e6e3f0` — secondary tonal surface, tab rail
- **Glass** `rgba(255,255,255,0.55)` — frosted card fill (always with backdrop-blur 20px + saturate 1.4)
- **Glass Edge** `rgba(255,255,255,0.55)` — 1px inner border on every glass card

### Ink
- **Ink** `#1a1830` — text, headings (deep indigo-black, slight purple undertone)
- **Ink 50** `#6b6987` — secondary text, mono labels

### Accent
- **Indigo** `#3d3a8a` — primary CTA, active panel ring, focus state
- **Indigo Soft** `rgba(61,58,138,0.12)` — focus ring background, hovered state

## 3. Typography

| Role | Font | Size | Weight | Leading | Tracking |
|------|------|------|--------|---------|----------|
| Hero | Spectral | 80px | 500 | 1.02 | -0.035em |
| Hero Italic Word | Spectral (italic) | 80px | 500 | 1.02 | -0.035em |
| H1 | Plus Jakarta Sans | 48px | 600 | 1.1 | -0.025em |
| H2 | Plus Jakarta Sans | 26px | 600 | 1.25 | -0.012em |
| Body | Plus Jakarta Sans | 17px | 400 | 1.62 | -0.005em |
| UI / Button | Plus Jakarta Sans | 14px | 600 | 1.4 | 0 |
| Caption | JetBrains Mono | 11px | 500 | 1.0 | 0.08em uppercase |
| Number | JetBrains Mono | 13px | 500 | 1.0 | 0 tabular-nums |

Spectral italic is the signature moment — exactly one word per headline gets the italic. Anything more and the page reads as a wedding invitation.

## 4. Buttons

### Primary (Indigo Rounded)
```css
background: #3d3a8a;
color: #f4f2fb;
padding: 11px 22px;
border-radius: 16px;
font-weight: 600;
```

The 16px radius matches the glass cards — the button reads as a solid indigo glass tile sitting alongside the frosted ones.

### Secondary (Glass)
```css
background: rgba(255,255,255,0.55);
backdrop-filter: blur(20px) saturate(1.4);
border: 1px solid rgba(26,24,48,0.10);
```

The secondary IS a glass tile — same blur, same border, smaller scale.

### Outline & Ghost
- Outline: transparent, 1px hairline at 18% ink
- Ghost: no border, ink-50, hover lifts to glass

## 5. Cards

```css
background: rgba(255,255,255,0.55);
backdrop-filter: blur(20px) saturate(1.4);
border: 1px solid rgba(255,255,255,0.55);
border-radius: 22px;
box-shadow: rgba(26,24,48,0.05) 0 1px 2px, rgba(26,24,48,0.04) 0 8px 24px -8px;
```

The `saturate(1.4)` is what separates this from generic 2018 glassmorphism — it pulls the lavender tint forward through the glass instead of greying it out. The 1px inner border at 55% white catches the page tint and reads as light bouncing off the front face of the pane.

## 6. Charts

Thin precise bars (4px wide, 5px gap). One bar in indigo, others in 22% ink. Line charts at 1.5px ink with a 10% indigo fill, ending in an indigo dot marker. NO gridlines — the glass card itself frames the chart.

## 7. Tabs

Pill tabs (9999px radius). Active = indigo-soft background fill, ink text, no border. Inactive = transparent, ink-50. Sits inside a glass rail.

## 8. Spacing

- Base 4px
- Scale: `4, 8, 12, 16, 20, 24, 32, 48, 64, 96`
- Section padding: 96px desktop, 48px mobile

## 9. Do's & don'ts

✅ **Do**
- Use real `backdrop-filter: blur(20px) saturate(1.4)` — the saturation lift is non-negotiable
- Hold the lavender-bone page surface — the tint that bleeds through the glass IS the system
- Reserve indigo for primary CTA + active panel ring + focus state — never as a background
- Use Spectral italic on exactly one word per headline — the calligraphic moment

❌ **Don't**
- Use white or grey backgrounds — the tint is what makes the glass read as glass
- Use `opacity: 0.5` instead of `backdrop-filter` — that is fake glass and reads as fog
- Use indigo as a fill or background — three surfaces only
- Use Spectral for body — Plus Jakarta Sans handles all prose; Spectral is accent only

---

## Tokens

> Generated from the same source the live preview renders from.
> Treat the values below as the contract — never substitute approximations.

### Colors

| Role      | Value |
|-----------|-------|
| primary   | `#1a1830` |
| secondary | `#6b6987` |
| tertiary  | `#1a1830` |
| neutral   | `#e6e3f0` |
| surface   | `#eeeaf5` |

### Typography

- **Display:** Spectral
- **Body:** Plus Jakarta Sans
- **Mono:** JetBrains Mono

| Role | size / leading / weight / tracking |
|------|------------------------------------|
| Hero | 5rem / 1.02 / 500 / -0.035em |
| H1   | 3rem / 1.1 / 600 / -0.025em |
| H2   | 1.625rem / 1.25 / 600 / -0.012em |
| Body | 1.0625rem / 1.62 / 400 / -0.005em |

### Radius

- sm: `10px`
- md: `16px`
- lg: `22px`
- pill: `9999px`

### Shadows

- **card:** `rgba(26,24,48,0.05) 0 1px 2px, rgba(26,24,48,0.04) 0 8px 24px -8px`
- **button:** `none`

### Borders

- **card:** `1px solid rgba(255,255,255,0.55)`
- **divider:** `rgba(26,24,48,0.10)`

### Buttons

Four variants, each fully tokenized. The preview renders from these exact values.

#### Primary

| Property | Value |
|----------|-------|
| shape | `rounded` |
| background | `#3d3a8a` |
| color | `#f4f2fb` |
| border | `none` |
| padding | `11px 22px` |
| fontWeight | `600` |
| fontSize | `0.875rem` |

#### Secondary

| Property | Value |
|----------|-------|
| shape | `rounded` |
| background | `rgba(255,255,255,0.55)` |
| color | `#1a1830` |
| border | `1px solid rgba(26,24,48,0.10)` |
| padding | `11px 22px` |
| fontWeight | `500` |
| fontSize | `0.875rem` |

#### Outline

| Property | Value |
|----------|-------|
| shape | `rounded` |
| background | `transparent` |
| color | `#1a1830` |
| border | `1px solid rgba(26,24,48,0.18)` |
| padding | `11px 22px` |
| fontWeight | `500` |
| fontSize | `0.875rem` |

#### Ghost

| Property | Value |
|----------|-------|
| shape | `rounded` |
| background | `transparent` |
| color | `#6b6987` |
| border | `none` |
| padding | `11px 16px` |
| fontWeight | `500` |
| fontSize | `0.875rem` |

### Charts

| Property | Value |
|----------|-------|
| variant | `thin-bars` |
| strokeWidth | `1.5` |
| fillOpacity | `0.1` |
| gridlines | `false` |
| barGap | `5px` |
| highlight | `single` |
| dotMarker | `true` |

---

## Pro tokens

> Production-fidelity tokens. States, density, motion, elevation,
> content rules and a measured WCAG contract — derived from the
> resting tokens unless explicitly authored.

### States

#### Button

- **hover** — bg: `rgba(26, 24, 48, 0.92)`, shadow: `0 4px 20px -8px rgba(26, 24, 48, 0.4)`
- **focus** — outline: `1.5px solid #1a1830`, outline-offset: `4px`
- **active** — transform: `translateY(1px)`, filter: `brightness(0.95)`
- **disabled** — opacity: `0.45`
- **loading** — opacity: `0.7`
- **selected** — bg: `#1a1830`, color: `#eeeaf5`

#### Input

- **hover** — border: `1px solid #1a1830`
- **focus** — border: `1px solid #1a1830`, shadow: `0 1px 0 0 #1a1830`
- **disabled** — opacity: `0.45`
- **error** — border: `1px solid #991B1B`, shadow: `0 1px 0 0 #991B1B`

#### Card

- **hover** — shadow: `0 8px 24px -12px rgba(15,23,42,0.14)`, transform: `translateY(-1px)`
- **selected** — border: `1px solid #1a1830`

#### Tab

- **hover** — color: `#1a1830`
- **focus** — outline: `1.5px solid #1a1830`, outline-offset: `3px`
- **selected** — color: `#1a1830`, border: `0 0 2px 0 solid #1a1830`

### Density

| Mode | padding × | row × | body | radius × | Use for |
|------|-----------|-------|------|----------|---------|
| compact | 0.72 | 0.78 | 0.8125rem | 0.85 | Information-dense — tables, IDEs, dashboards |
| comfortable | 1 | 1 | 0.9375rem | — | Default — most product UI |
| spacious | 1.35 | 1.3 | 1rem | 1.15 | Editorial — marketing, long-form, settings |

### Motion

**Signature — Page turn.** Deliberate, measured motion — like turning a magazine page. Never jerky, never overdone.

```css
transition: all 320ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
```

| Token | Value |
|-------|-------|
| duration.instant | `80ms` |
| duration.fast | `180ms` |
| duration.base | `320ms` |
| duration.slow | `500ms` |
| easing.standard | `cubic-bezier(0.25, 0.46, 0.45, 0.94)` |
| easing.decelerate | `cubic-bezier(0.0, 0, 0.2, 1)` |
| easing.accelerate | `cubic-bezier(0.4, 0, 1, 1)` |
| easing.spring | `cubic-bezier(0.5, 1.2, 0.6, 1)` |

### Elevation

Five-level scale, system-specific recipe.

| Level | Shadow | Recipe |
|-------|--------|--------|
| level0 | `none` | Hairline only — typical editorial resting state. |
| level1 | `0 1px 2px rgba(15,23,42,0.04)` | Barely visible — list rows, dividers. |
| level2 | `0 8px 24px -12px rgba(15,23,42,0.12)` | Pull-quote, sidebar — soft lift. |
| level3 | `0 16px 40px -16px rgba(15,23,42,0.18)` | Cover story card — clear lift. |
| level4 | `0 32px 80px -24px rgba(15,23,42,0.28)` | Modal — overlays the layout, with scrim. |

### Content

- **measure:** `60ch` (max line length for body prose)
- **paragraph spacing:** `1.5em`
- **list indent:** `1.75em`
- **list gap:** `0.55em`
- **link:** color `#1a1830`, underline `always`
- **blockquote:** border `4px solid #1a1830`, padding `0.4em 0 0.4em 1.5em`
- **code:** background `rgba(26, 24, 48, 0.06)`, color `#1a1830`

### Accessibility (WCAG 2.1)

**Overall:** AA-Large

| Pair | Ratio | Required | Grade | Suggested fix |
|------|-------|----------|-------|---------------|
| Body text on surface | 14.56:1 | AA | AAA | — |
| Body text on canvas | 13.65:1 | AA | AAA | — |
| Muted text on surface | 4.44:1 | AA | AA-Large | `#666581` → 4.73:1 (AA) |
| Accent on surface | 14.56:1 | AA-Large | AAA | — |
| Accent on canvas | 13.65:1 | AA-Large | AAA | — |
