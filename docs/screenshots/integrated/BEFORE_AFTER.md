# Design review, October 2026: before and after

The screenshots in this folder show the app after the review: `desktop-*` and `phone-*` are
dark, and `light/` holds the key screens in the light theme. They are all synthetic (the
mock library). The earlier set is in git at `1e3007a` (`git show 1e3007a:docs/screenshots/integrated/<file>`).
`docs/DESIGN_PRINCIPLES.md` §2 has the resulting tokens and component rules.

The whole set was rendered again when the root text size became the browser's 16 px: until
then it was 14 px, and type and spacing showed at 14/16 of the sizes in the design tables
(interface text 12.25 px for 14, a page title 24.5 px for 28). Photos are no smaller for it:
the laptop's side column is still 224 px.

> **Rows marked † are superseded** by the redesign that followed
> (`docs/superpowers/specs/2026-10-08-ui-redesign-design.md`); the table is kept as the record
> of this review. The rail became a top bar on a laptop and a floating dock on a phone, with
> an account menu. The date scrubber became the time ruler. The selection bar became a
> floating glass pill. The serif look with its indigo accent is now the Album theme only: the
> default, Safelight, sets titles in Hanken Grotesk and figures in Martian Mono, with an amber
> accent. The screenshots in this folder are taken from the app as it is, so they show the
> redesign and no longer the "After" column of the marked rows; `DESIGN_PRINCIPLES.md` §2
> describes today's look.

| Area | Before | After |
|---|---|---|
| Identity † | System sans everywhere, #111 page, red-orange accent | Newsreader (serif, optical sizes) for titles, dates and captions; Instrument Sans for the interface; both self-hosted. Deep graphite or paper page; indigo-ink accent |
| Tokens | 5 colours, 5 sizes, ad-hoc rem spacing | Colour, type scale (12/14/16/20/28/40), 4 px spacing scale, radii, target size and motion tokens in both themes; components use only tokens |
| Group labels | Tracked uppercase ("YEAR", "SOURCES") | Sentence case, 12 px semibold, secondary ink |
| Controls | Native checkboxes and radios, red focus boxes around fields | Drawn checkboxes and radios in ink; fields are underlines that turn indigo on focus; quiet words with a hover wash; one ink-filled primary per form |
| Rail † | Words only, current item in brighter grey | Italic "Photos" wordmark; current item in full ink and semibold; hover wash |
| Library † | Small sans month labels, plain circle on selected photos | Serif month headings with the count beside them; indigo frame plus a check on selection; heart drawn as SVG; scrubber on a hairline spine with a tick for "now" |
| Selection bar † | Count in the old accent | Count in the accent at 600 weight; the More menu is a raised sheet of 44 px rows |
| Loupe (desktop) † | Actions written over the photo with a text shadow | Photo actions in a band above the photo, so nothing covers it; SVG chevrons; serif date and italic place in the sidenote |
| Loupe (phone) | Toolbar wrapped onto two lines over the photo | Close and Info at the top, the photo actions on one line at the bottom within thumb reach; Info opens as a raised bottom sheet above that bar |
| Filters † | Uppercase headings; count under "Filters" | Serif title with the count inline; sentence-case groups; the selected year in full ink and weight; phone sheet with a sticky header and 44 px rows |
| Dialogs † | Flat boxes on the page colour | Raised surface, 8 px radius, serif title, 120 ms open; on a phone every dialog is a bottom sheet |
| Calendar † | "Darker ink" legend (wrong in the dark theme) | "Stronger ink, more photos"; serif year headings; still one hue and zero-based |
| Map | Orange chosen dot; land drawn in hairline grey | One ink for every place, indigo for the chosen one; land a step lighter than the sea; an empty state |
| Albums † | Small titles | Album covers captioned in the serif; the album page opens with a 40 px display title and an italic description |
| People † | Uppercase group labels | Serif group titles and names; unnamed people in italic |
| Search † | Field with a red focus box | The query is set in the serif on an underline; a drawn clear cross; empty and no-result states that suggest what to try |
| Settings | Uppercase section labels | Section titles in the left margin, like a book's margin heads (stacked on a phone) |
| Admin † | Mixed sizes; attention shown only as a border line | Serif section titles with their actions on the same baseline; "needs attention" as an ink rule in the margin; monospace paths; mobile table as stacked rows |
| Setup and sign-in † | Small title, the Sign in button with no left padding | 40 px serif "Welcome" and italic "Photos", a one-line lede, labelled underline fields, a full-size primary button |
| Toasts | Text on the page colour | A raised slip with Undo in bold |
| Phones | Mixed target sizes; iOS zoomed into small fields | 44 px controls on touch screens; 16 px fields; safe-area padding in the nav, sheets and loupe; hover styles only on devices that can hover |
| Empty states † | One grey sentence | A serif sentence saying what is (not) here, then a plain one saying what to do |
