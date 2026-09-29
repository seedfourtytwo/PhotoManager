# Design principles

Inspired by Edward Tufte. In a photo app **the photos are the data**. Everything that is not a
photo — chrome, borders, badges, backgrounds — is non-data ink to be reduced until removing
more would hurt understanding.

## 1. Rules

1. **Maximise photo ink.** Photos use as much of the screen as possible; no cards, drop shadows,
   rounded frames or gradients around them. Gutters are 2–4 px.
2. **Never crop without consent.** Grids are *justified* (true aspect ratios). Crops only exist
   inside album frames, chosen by the user.
3. **Erase non-data ink.** No borders where whitespace works; no icon when a word is clearer;
   one hairline (1 px, low-contrast) is the strongest divider we use.
4. **Data density with calm.** Show a lot, quietly: many thumbnails, small type for metadata,
   one accent colour used only for selection and focus.
5. **Small multiples over dashboards.** Comparisons (years, places, people) are shown as
   repeated, identically scaled small panels — never mismatched charts.
6. **Charts are honest.** Zero-based scales for counts; no 3D, no pie charts, no dual axes;
   direct labels instead of legends; the calendar heat map uses one sequential hue.
7. **Words are part of the graphic.** Dates, places and names sit next to what they describe
   (margin notes, like Tufte's sidenotes), not in tooltips only.
8. **Layering and separation by value, not colour.** Secondary information is lighter grey,
   not a different colour.
9. **Motion only to explain.** Transitions ≤ 150 ms, used to show where something went
   (photo zooms into loupe). Respect `prefers-reduced-motion`.
10. **Same thing, same place.** Laptop and phone share the information architecture; only the
    layout adapts.

## 2. Tokens (starting point)

| Token | Light | Dark (default for viewing) |
|---|---|---|
| `--bg` | #FAFAF8 | #111111 |
| `--ink` | #1A1A1A | #EDEDED |
| `--ink-2` (secondary) | #6B6B6B | #9A9A9A |
| `--hairline` | #E4E2DD | #262626 |
| `--accent` (selection/focus only) | #B3261E | #E0674F |
| `--gutter` | 3 px | 3 px |

Type: one serif for titles and album text (e.g. *Source Serif 4* / *ET Book*), one sans for UI
(e.g. *Inter*), tabular numerals for dates and counts. Scale: 12 / 14 / 16 / 20 / 28.
All UI text meets WCAG AA contrast; photos may sit on `--bg` in either theme.

## 3. Layout by device

| | Laptop (≥ 1024 px) | Phone (< 640 px) |
|---|---|---|
| Navigation | slim left rail: Library · Map · People · Albums · Search | bottom bar, same 5 items |
| Filters | right margin, always visible, collapsible | bottom sheet |
| Loupe metadata | right margin "sidenote" | swipe up |
| Selection | click / shift-click / drag-lasso | long-press then tap |
| Grid row height | ~220 px | ~110 px, pinch to change |

## 4. Print design (albums)

- Generous margins, consistent baseline for captions, one serif family per theme.
- Layouts are a small, well-made set rather than infinite freedom.
- Every page has a bleed-aware safe area; nothing important within 5 mm of trim.
- Captions are text, never baked into the image.

## 5. Review checklist (tick in PR)

- [ ] Could any border, box, shadow or icon be removed without losing meaning?
- [ ] Are photos shown at true aspect ratio (unless in a user-chosen album frame)?
- [ ] Is the accent colour used only for selection/focus?
- [ ] Charts: zero-based, directly labelled, no chartjunk?
- [ ] Works at 375 px wide and at 1440 px wide?
- [ ] Keyboard reachable, visible focus, AA contrast, reduced motion respected?
