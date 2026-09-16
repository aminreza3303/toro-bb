---
version: alpha
name: "Heritage"
description: "Late-night tooling. Near-black paper, phosphor accent, mono labels. Density is compact; chrome stays quiet so the work is the interface."
colors:
  primary: "#10211A"
  secondary: "#4A5C54"
  tertiary: "#15803D"
  neutral: "#F3F7F4"
  surface: "#FFFFFF"
  on-surface: "#0A0A0A"
  on-primary: "#FFFFFF"
  on-tertiary: "#FFFFFF"
  error: "#C44545"
  dark-primary: "#E7F9EE"
  dark-secondary: "#7C9086"
  dark-tertiary: "#3DDC84"
  dark-neutral: "#0B1210"
  dark-surface: "#121A17"
  dark-on-surface: "#FFFFFF"
  dark-on-primary: "#0A0A0A"
  dark-on-tertiary: "#0A0A0A"
  dark-error: "#FF6B6B"
typography:
  headline-lg:
    fontFamily: "IBM Plex Sans Arabic"
    fontSize: 40px
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: -0.02em
  headline-md:
    fontFamily: "IBM Plex Sans Arabic"
    fontSize: 28px
    fontWeight: 600
    lineHeight: 1.2
  body-lg:
    fontFamily: "IBM Plex Sans Arabic"
    fontSize: 18px
    fontWeight: 400
    lineHeight: 1.6
  body-md:
    fontFamily: "IBM Plex Sans Arabic"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.6
  body-sm:
    fontFamily: "IBM Plex Sans Arabic"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
  label-md:
    fontFamily: "IBM Plex Sans Arabic"
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1
    letterSpacing: 0.02em
rounded:
  sm: 2px
  md: 4px
  lg: 8px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 20px
  xl: 32px
  gutter: 16px
  margin: 20px
components:
  button-primary:
    backgroundColor: "{colors.tertiary}"
    textColor: "{colors.on-tertiary}"
    rounded: "{rounded.md}"
    padding: 8px
  button-primary-hover:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    rounded: "{rounded.md}"
    padding: 8px
  button-ghost:
    backgroundColor: transparent
    textColor: "{colors.secondary}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
    padding: 8px
    height: 44px
  input-error:
    textColor: "{colors.error}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.lg}"
    padding: 20px
  chip:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.primary}"
    rounded: "{rounded.full}"
    padding: 8px
  chip-selected:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
  nav:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.primary}"
    height: 64px
  checkbox:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.tertiary}"
    rounded: "{rounded.sm}"
    size: 20px
  radio:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.tertiary}"
    rounded: "{rounded.full}"
    size: 20px
  textarea:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
    padding: 8px
    height: 120px
  switch:
    backgroundColor: "{colors.secondary}"
    rounded: "{rounded.full}"
    width: 44px
    height: 24px
  switch-on:
    backgroundColor: "{colors.tertiary}"
  tabs:
    textColor: "{colors.secondary}"
  tab-active:
    textColor: "{colors.primary}"
    backgroundColor: "{colors.surface}"
  alert:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.primary}"
    rounded: "{rounded.md}"
  alert-error:
    textColor: "{colors.error}"
  badge:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.primary}"
    rounded: "{rounded.full}"
  badge-accent:
    backgroundColor: "{colors.tertiary}"
    textColor: "{colors.on-tertiary}"
  list-item:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    padding: 12px
  table:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
  tooltip:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.sm}"
    padding: 8px
  avatar:
    backgroundColor: "{colors.tertiary}"
    textColor: "{colors.on-tertiary}"
    rounded: "{rounded.full}"
    size: 40px
  dropdown:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
    height: 44px
  pagination:
    textColor: "{colors.secondary}"
  pagination-active:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
  progress:
    backgroundColor: "{colors.neutral}"
    rounded: "{rounded.full}"
    height: 8px
  progress-bar:
    backgroundColor: "{colors.tertiary}"
  empty:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.secondary}"
    rounded: "{rounded.lg}"
    padding: 20px
  dialog:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.lg}"
    padding: 20px
---

# Heritage

## Overview

Late-night tooling. Near-black paper, phosphor accent, mono labels. Density is compact; chrome stays quiet so the work is the interface.

Editorial and institutional. Deep green ink on pale green paper, with bright green reserved for the primary action and focus.

Place this file at the repository root as `DESIGN.md`. Point coding agents at it from `AGENTS.md` (or `CLAUDE.md`) so they read tokens before writing UI. Tokens are the source of truth; this prose tells the agent when *not* to improvise.

Display face: **IBM Plex Sans Arabic**. Body face: **IBM Plex Sans Arabic**. Labels / meta: **IBM Plex Sans Arabic**. These faces cover Arabic/Persian script. Do not render Persian in Inter, Public Sans, or other Latin-only faces. If the webfont is unavailable, use the bundled Vazirmatn fallback.

Specified components: nav, button, input, textarea, card, chip, badge, alert, tabs, list, table, checkbox, radio, switch, tooltip, avatar, dropdown, pagination, progress, empty, dialog.

## Colors

Ship **light** and **dark**. Unprefixed tokens are light. Dark tokens use the `dark-` prefix (`dark-surface`, `dark-primary`, …). At runtime, map the `dark-*` set onto the unprefixed names when the document is dark. Do not invent extra hues mid-render.

### Light

- **Primary (#10211A):** Brand ink. Headlines, key text, and selected chrome.
- **Secondary (#4A5C54):** Muted text, borders, captions, unused nav links.
- **Tertiary (#15803D):** The only chromatic accent. Primary actions, focus rings, selected glyphs.
- **Neutral (#F3F7F4):** Page paper / canvas behind surfaces.
- **Surface (#FFFFFF):** Cards, inputs, raised panels.
- **On-surface (#0A0A0A):** Default text on surface and neutral.
- **Error (#C44545):** Validation and destructive text only — never decoration.

### Dark

- **Primary (#E7F9EE):** Ink on dark paper.
- **Secondary (#7C9086):** Muted text and borders.
- **Tertiary (#3DDC84):** Accent / primary action fill.
- **Neutral (#0B1210):** Page paper.
- **Surface (#121A17):** Raised panels.
- **On-surface (#FFFFFF):** Default text.
- **Error (#FF6B6B):** Destructive text only.

Body text on surface must keep WCAG AA (4.5:1) in **both** schemes. If a new color is required, add a token here first; do not inline hex in components.

## Typography

- **Headlines:** IBM Plex Sans Arabic, roman only — no italic headers. Weight 600–700. Cap headline-lg at ~7 words.
- **Body:** IBM Plex Sans Arabic at 16px (body-md) for UI copy; body-lg for marketing lead. Line-height 1.6.
- **Labels:** IBM Plex Sans Arabic, 12px. Fine for overlines, chips, and table meta — not for paragraphs.

IBM Plex Sans Arabic is the only family. Do not introduce a second face. Do not fake hierarchy by coloring a headline in tertiary.

### Local font availability

IBM Plex Sans Arabic was not available in the local font locations searched on
2026-09-16. The existing local demo fallback remains
`web/fonts/Vazirmatn.ttf`, served at `/fonts/Vazirmatn.ttf`; it should be used
until a properly bundled IBM Plex Sans Arabic webfont is available.

## Layout

Density is **compact**. Use the spacing scale; do not pick padding by eye.

- Base rhythm: 8px / 12px / 20px.
- Gutter 16px, page margin 20px.
- Desktop content maxes at 1200px. Mobile is a single column; no two-line tap labels.
- Group related controls by proximity, not by extra boxes.

## Elevation & Depth

Cards sit on surface against neutral paper. A soft stacked shadow is allowed on surface cards; do not stack shadows on nested elements. Borders stay 1px in secondary at reduced opacity. No fake browser chrome, no glassmorphism.

## Shapes

Shape language is architectural. Buttons and inputs use rounded.md (4px). Cards may go to rounded.lg (8px). Do not mix a pill button with a sharp card on the same view.

Pick one radius family and keep it. Mixing sharp cards with pill buttons is a don't.

## Components

### Nav

A quiet bar: wordmark on the start edge, two or three text links, one primary control on the end edge. No mega-menus. Nav height stays 64px; links use body-md in the secondary color and turn primary on the current page.
### Buttons

- **Primary** fills with `tertiary` and `on-tertiary` text. One per view.
- **Secondary** is an outlined surface button with `primary` text.
- **Ghost** is text-only in `secondary`, used for low-emphasis actions.
- Minimum height 44px. Disabled state is 40% opacity, not a new color.
- Hover may darken toward `primary`; never scale or bounce.
### Input fields

Visible label above the field, never placeholder-as-label. Default height 44px, 1px border in secondary at ~40% opacity. Focus uses a 2px tertiary ring with 2px offset. Error text sits under the field in the error color; the border also turns error.
### Cards

Surface on neutral, large radius, internal padding from the density scale. Hierarchy is title (headline-md) then body-md in secondary. If the card is clickable, the whole card is the hit target and the cursor is pointer; do not nest a competing primary button unless it is a distinct action.
### Chips

Pill shape always. Unselected chips sit on neutral with primary text. Selected chips invert to primary / on-primary. Do not use chips as a substitute for primary buttons.
### Selection controls

Checkboxes are square with sm radius; radios are full circles; switches are 44×24 pills. The selected glyph/track uses tertiary. Labels sit beside the control in body-md. Hit area is at least 44×44px.
### Textarea

Same chrome as input: visible label, 1px secondary border, tertiary focus ring. Minimum height 120px. Do not grow the field with JS autosize unless the product is a composer.
### Badges

Tiny status, never a button. Neutral/primary for default; tertiary/on-tertiary for the one accent badge per cluster. Pill radius. No icons-as-emoji.
### Alerts

Full-width surface on the section, not a modal. Info uses primary text on neutral; error uses the error color for the title and a 1px error border. One action max, secondary or ghost.
### Tabs

Equal-height text tabs. Active tab is primary ink on surface with a 2px tertiary underline (or a filled chip on pill systems). Inactive is secondary. No nested tabs.
### Lists

Row = leading avatar or glyph, title in primary, meta in secondary. Dividers are 1px secondary at 20% opacity. The whole row is the hit target when navigational.
### Tables

Header in label-md / secondary. Cells in body-md. Row hover is a 6% primary wash, not a scale. Prefer a stacked definition list below 700px instead of horizontal scroll.
### Tooltips

Primary fill, on-primary text, sm radius. Appear on focus immediately and on hover after 800ms. Never the only way to learn a control's name.
### Avatars

40px default, full circle. Initials in on-tertiary on tertiary. No random photo URLs; use a placeholder block if the product has no asset.
### Dropdowns

Looks like an input at rest. Open menu is a surface card, sm shadow, items at 44px height. Selected item uses tertiary text, not a new fill. Keyboard: arrow keys + Enter + Escape.
### Pagination

Current page is primary / on-primary. Neighbors are ghost text in secondary. Keep the control on one row; never wrap page numbers under the table. Prefer previous/next plus the current page on mobile rather than a long page strip.
### Progress

Track sits on neutral, 8px tall, full pill. Fill is tertiary only. Pair with a body-sm percent or step label in secondary — never color the label in tertiary.
### Empty states

Surface card, centered copy, one secondary or primary action. No illustration libraries, no emoji. Title in headline-md, body in secondary. The empty state is a destination, not a toast.
### Dialogs

A surface card, not a full-screen takeover on desktop. Title + one paragraph + two actions (primary + ghost). Dim the canvas behind with a 40% primary wash; do not blur. Escape and the ghost action both dismiss.

## خرید سازمانی: ساختار تجربه

- ورودی اصلی، ویترین کالا با جست‌وجو، دسته‌بندی و کارت قیمت است؛ فرم چندقلمی پس از انتخاب کالا می‌آید.
- کارت کالا نام، دسته، تعداد پیشنهاد پذیرفته‌شده و کمترین قیمت بسته در snapshot را نشان می‌دهد. جزئیات، اندازهٔ بسته، فروشنده، موجودی، زمان تحویل و منشأ را آشکار می‌کند.
- افزودن کالا فهرست خرید را پر می‌کند؛ کاربر تعداد، بودجه، زمان و اولویت را پیش از مقایسه ویرایش می‌کند.
- معرفی خرید سازمانی بخش مستقلی دارد. مسیر شرکت ثبت‌شده و دارندهٔ پروانهٔ کسب فقط چشم‌انداز محصول‌اند تا زمانی که احراز هویت و ثبت‌نام واقعی پیاده شوند.
- دادهٔ ساختگی، نبود سفارش و پرداخت واقعی، و وضعیت اعلامی فاکتور نزدیک به تصمیم خرید نمایش داده شوند.
- ساختار از [ویترین دیجی‌کالا بیزینس](https://b2b.digikala.com/) و [صفحهٔ ثبت‌نام سازمانی](https://www.digikala.com/landings/business-registration/) الهام گرفته است؛ لوگو، رنگ و اجزای آن برند نباید کپی شوند.

## Do's and Don'ts


- Do use tertiary for a single primary action per screen.
- Don't introduce new hex values in JSX/CSS; add a token first.
- Do keep tap targets at least 44×44px.
- Don't use emojis as icons. Use a consistent SVG set (Lucide or Heroicons).
- Do write visible labels on inputs; placeholders are hints, not labels.
- Don't italicize headings.
- Do honor `prefers-reduced-motion`: no layout motion, opacity-only if needed.
- Don't animate focus rings. They appear instantly.
- Do default text alignment to the product language (RTL for Persian UI).
- Do implement both light and dark from the `dark-*` tokens — never guess a dark palette.
- Don't clone a competitor's brand. These tokens are the system — follow them even on new pages.
