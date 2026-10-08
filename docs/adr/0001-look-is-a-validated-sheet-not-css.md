# A look is a validated sheet of values, never CSS

Each account can have its own appearance, set by the admin and later by a local AI model from a
sentence. We store that as a small sheet of named values (a theme, a mode, a few range-limited
dials and on/off switches) that the server validates, and we do not store or accept CSS, custom
colours or per-account code.

## Considered options

- **Free CSS per account.** Most flexible, and what was first asked for. Rejected: CSS can load
  remote URLs and so leak what is on screen, which breaks "nothing leaves the machine"; it binds
  to internal class names and breaks silently on any refactor; and a small local model writing
  free CSS will eventually produce an unreadable or unusable page.
- **Custom colour values per account.** Rejected: needs a contrast checker and lets one typo make
  an account's app unreadable. A new palette is added as a theme that ships with the app instead.
- **Different screens per account.** Rejected: one app to maintain per family member. Layout
  differences are switches from a fixed list; anything else becomes a feature for everyone.

## Consequences

- A look cannot make the app unusable, and "reset look" always works.
- Asking for something no dial or switch covers means a code change, not a data change.
- The AI's job is filling in a form, which structured output makes reliable.
