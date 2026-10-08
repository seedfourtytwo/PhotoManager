# Photo Assistant

A self-hosted family photo library: it pulls photos from the family's devices and folders,
keeps them on the family's own machines, and lets each person browse, find, arrange and print them.

## Language

### People

**Account**:
One person's sign-in, with a role (admin, member or guest) and their own favourites, hidden items and look.
_Avoid_: User, profile, login

**Admin**:
The account role that runs the installation: accounts, sources, backups, and every account's look.
_Avoid_: Owner, superuser

### Places in the app

**Today**:
The opening page: a short, regularly refreshed set of heroes, above the newest photos.
_Avoid_: Home, feed, dashboard

**Hero**:
A set of photos the app assembled by itself and offers on Today, such as a throwback or a weekly pick.
_Avoid_: Memory, highlight, story, suggestion

**Library**:
Every photo the account may see, in date order.
_Avoid_: Timeline, gallery, all photos

**Collections**:
The page that gathers the ways of grouping photos: people, places, albums, calendar.
_Avoid_: Explore, browse, categories

**System**:
The admin-only page showing the installation's health, sources, running work, accounts and backups.
_Avoid_: Admin page, dashboard, control panel

**Chip**:
One active filter shown as a removable label; the set of chips is what the Library currently shows.
_Avoid_: Tag (a tag is a label on a photo), token, pill

**Time ruler**:
The ticked scale of years that shows where in time the Library is scrolled and can be dragged to move.
_Avoid_: Scrubber, scrollbar, timeline

### Appearance

**Look**:
Everything about how the app appears for one account: its theme, its mode, its dials and its switches. Set by the admin; the account itself chooses only the mode.
_Avoid_: Skin, style, custom CSS, preferences

**Theme**:
A named, complete set of colours, corners and typefaces that ships with the app.
_Avoid_: Palette, preset, skin

**Safelight**:
The default theme: darkroom greys, an amber accent, data in monospace.

**Album**:
As a theme name, the earlier serif "family album" appearance. Unrelated to a photo album; say "the Album theme".

**Mode**:
Whether a theme is shown dark, light, or following the device.
_Avoid_: Colour scheme

**Dial**:
One named, range-limited adjustment on top of a theme, such as accent hue or text size.
_Avoid_: Setting, override, variable, token

**Switch**:
One choice from a fixed list that changes what an account's app shows or where it starts, such as whether Today appears.
_Avoid_: Layout, feature flag, option

### Backups

**Backup place**:
An enabled backup target, or the Proton Drive copy of one. The copy is shown as a copy because it does not survive a damaged repository.
_Avoid_: Destination, location

**Skipped run**:
A backup or copy not attempted because its place is not connected. It is not a failure and not an attempt; the app looks again every 15 minutes.
_Avoid_: Failed run, missed run

**Protected**:
At least two backup places are up to date. When not, admins see a banner on every page.
_Avoid_: Safe, backed up
