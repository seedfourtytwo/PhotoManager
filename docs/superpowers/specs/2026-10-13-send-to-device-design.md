# Send to a device: a one-time link for chosen photos

Date: 2026-10-13. Area: `handover` (domain, app, adapters, api), the web app (a dialog, a
receiving page, a small QR drawer), docs. Off by default; C turns it on.

This note was written before the code and revised the same day with C's answers (marked
**Decided**). "As built" at the end says where the code differs from the first draft.

## Goal

C or his partner picks photos, the app shows a QR code and a link, another device opens it
and downloads those photos straight from the home server. The other device needs no account
and no app: any phone browser. The link works once, for ten minutes.

The phone's own share sheet (AirDrop, Quick Share) is a separate piece of work (`feat/share`).
This is the app's own way.

## What is true today about https (and who can therefore receive)

- The app listens on `127.0.0.1:8420` in plain http. The only https address is the one
  `tailscale serve` puts in front of it: `https://<machine>.<tailnet>.ts.net`. Only devices
  on C's Tailscale network reach it.
- A visitor's phone on the home Wi-Fi without Tailscale cannot reach the app at all today,
  with or without this feature: nothing listens on the home network.
- The app knows truthfully whether a request arrived over https: uvicorn believes the
  `X-Forwarded-Proto` header only from the addresses in `PA_TRUSTED_PROXIES` (default: this
  machine, where `tailscale serve` runs). The session cookie's `Secure` flag already relies on
  it. A request that reaches a port directly cannot claim https.

So there are two kinds of receiver, and the feature serves both:

| Receiver | Address in the link | Encrypted |
|---|---|---|
| on the tailnet (C's and his partner's own devices) | the Tailscale https address | yes |
| any phone on the home Wi-Fi | a home address an admin sets, served by a second small door | **no** (plain http) |

## Decided by C (2026-10-13)

1. A link that needs no account is acceptable, single use. Off by default behind an admin
   switch, ten minutes, members and admins only, access checked again when collected, a page
   with a button before anything is sent, a trail with Cancel: as proposed.
2. **Https is not mandatory.** Over plain http the sender is warned in plain words before
   every link and must choose "Send anyway"; nothing remembers the choice. The link records
   that it was unencrypted; the trail and the receiving page say so. Everything else is as
   strict as over https. A second admin switch, on by default, allows unencrypted sending.
3. **"Remove details before sending"**, on by default (privacy first; the default is a
   setting C can flip): the copy carries no location, camera or lens, capture settings,
   dates, embedded thumbnail, XMP or IPTC, and no original file name. It stays upright and
   keeps its colour profile. The library file and the source file are never touched.
4. **The QR code is a requirement**, and it must carry an address the other phone can open.

## The flow

Sender (signed in, member or admin):
1. Selects photos (or opens one) → More → **Send to a device**.
2. The dialog says what will happen, offers "Remove details before sending" (ticked), and,
   when the link can point to two addresses, asks where the other device is. If the chosen
   address is not https it shows the warning and the button reads **Send anyway**; otherwise
   **Show the code**.
3. Then: the QR code, the link with Copy, "3 photos · 8.4 MB · details removed", a
   countdown, and "Waiting for the other device…", which becomes "Downloaded on another
   device." Closing the dialog while it still waits cancels the link.

Receiver (no account):
1. Scans the code or opens the link: "C is sending you 3 photos", whether the link is
   encrypted, whether details were removed, until when it works, and one button, **Download**.
2. The tap downloads one JPEG, or a ZIP of several. The link is now used up.
3. A link that no longer works says so in one sentence.

## Design

### The hand-over (pure rules, `domain/handover.py`)

A fixed list of photo ids, who made it, when it runs out, how often it may be collected
(1), whether its link is https, whether details are removed, and when it was collected or
cancelled. Its state is worked out, never stored: `waiting`, `redeemed`, `expired`,
`cancelled`.

- Runs out after 10 minutes (`PA_SEND_TO_DEVICE_MINUTES`, 1 to 60). At exactly the expiry
  time it is expired.
- At most 100 photos and about 1 GB per hand-over.
- Only a waiting hand-over can be cancelled or collected.

### The token and the link

- 256 random bits from the operating system, URL-safe text. Only its SHA-256 is stored, as
  for sessions and device tokens, and compared in constant time. Shown once, to the sender.
- The link is `<address>/receive.html#<token>`. The token sits after the `#`: browsers never
  send that part to a server, so it is in no access log, no proxy log and no `Referer`. The
  receiving page reads it and sends it in the body of a POST.
- So a link preview (a chat app fetching the link) or a QR scanner's prefetch gets a page with
  no token in it and cannot use the link up. The photos leave only on the tap.

### Which address goes into the link

- **Here**: the address the sender is browsing at, unless that is the server's own
  (`localhost`): no other device can open that.
- **Home**: `PA_SEND_TO_DEVICE_ADDRESS`, set by an admin, for phones on the home Wi-Fi.
- With both, the dialog asks and starts on the encrypted one. With neither, it shows no code
  and says why, and what to do (an admin is told the setting; a member whom to ask).

The app cannot work out a home address by itself (in Docker it does not even see the
server's own), so it never guesses one into a QR code.

### The second door

Opening the whole app to the home Wi-Fi would put the sign-in screen and every PIN typed
there on the network in clear text. So the home address is served by a second, separate
listener (`PA_SEND_TO_DEVICE_LISTEN`, e.g. `0.0.0.0:8421`): a small app with the receiving
page and the two token routes, and nothing else. The library stays on `127.0.0.1` behind
Tailscale. Nothing is in front of the door, so on it a request is never https.

### Encrypted or not, truthfully

A link is "encrypted" when its address is https. For "here" that is what the server itself
knows about the request (above); when it cannot know, it is not encrypted. An unencrypted
link needs the admin's switch (`PA_SEND_TO_DEVICE_UNENCRYPTED`, default on) and the sender's
yes on that request; the server enforces both, not only the dialog. A link made as https is
never honoured over plain http: it is refused there and cancelled, because its token has
just crossed the network in the clear.

"Encrypted" here means in transit (TLS, inside Tailscale's own encryption). It is not
end-to-end: the home server reads the photos, which it holds anyway.

### Who may send what

Members and admins, not guests. Every photo must be visible to the sender through the
existing access rule and at download level; another person's private photos therefore never
qualify. The same check runs again when the link is collected, as the sender: a photo the
sender lost access to meanwhile is left out, and a sender whose account was disabled sends
nothing.

### The copy that is sent

A full-size JPEG with the sender's edits (the Download dialog's "With edits"), which any
phone opens; one photo as a file, several as a streamed ZIP. It goes through Download's own
path: libvips renders a temporary copy in `data/tmp`, removed once sent. With details
removed, that copy is saved with no metadata but its colour profile and named `photo.jpg`,
`photo_2.jpg`…; otherwise it keeps its metadata and its file name.

### The receiving side (no session, so guarded differently)

- `POST /api/handovers/look` says how many photos and from whom; `POST
  /api/handovers/collect` sends them and uses the link up.
- One answer for a wrong, used, expired or cancelled token, so nobody can probe which is
  which. The page turns it into one sentence.
- Wrong tokens are counted per address (10 in 15 minutes) and overall (100 in 15 minutes),
  then refused with "wait"; the PIN limit's idea, kept in memory.
- Collecting is one atomic database update: of two taps at the same moment, one wins.
- Never cached; the page may only run its own script and talk to its own server.

### Storage and the trail

One new table, `handover` (migration 0028). Its rows are also the record C reads in Settings:
who sent how many photos, when, encrypted or not, details removed or not, whether and when
they were collected, from which address and what kind of device. Members see their own,
admins everyone's; a waiting one has Cancel. The daily clean-up that prunes the AI log
deletes rows after 90 days.

### The switches

All are environment variables like every other setting (`docs/guides/settings.md`):
`PA_SEND_TO_DEVICE` (default `false`: nothing shows and every address of the feature is a
404), `…_MINUTES`, `…_UNENCRYPTED`, `…_REMOVE_DETAILS`, `…_ADDRESS`, `…_LISTEN`.

## Threat model, in plain words

| Someone… | What happens |
|---|---|
| sees the QR code over your shoulder and scans it first | They get the photos, if their device can reach the address. The sender's dialog then says "Downloaded" before the intended person tapped: that is the warning sign. One use limits it to those photos, once. |
| gets the link forwarded in a chat | Same: whoever opens it first, within 10 minutes, on that network, gets the photos. The chat app's own preview cannot use it up. |
| replays the link later | Refused: used, expired and cancelled all read "does not work any more". |
| guesses tokens | 256 bits cannot be guessed; the counter stops the trying anyway. |
| reads the server's or the proxy's logs | The token is not in them (it is never part of an address). The trail holds only its hash. |
| listens on the Wi-Fi, https link | Sees Tailscale's encrypted traffic, nothing else. |
| listens on the Wi-Fi, unencrypted link | **Sees the photos, and the token.** With the token they could even collect first. This is what the warning is for: only send what you would not mind them seeing. |
| is a guest on the Wi-Fi and pokes at the door | Finds the receiving page and two routes that want a token. No sign-in screen, no library. |
| steals the receiving phone | Has the downloaded photos, like any file on that phone. The link in its history is used up. |
| steals the sender's unlocked, signed-in phone | Can send photos to themselves, as they could already download them. |
| runs a program on the home server itself | Can claim "this was https" to the app. Same trust the sign-in cookie already places in the server. |

Whatever is done, the photos are only as private as the device that received them.

## Deliberately not built

- **Browser-to-browser transfer (WebRTC).** It needs a signalling server and often a relay,
  both devices awake in a browser at once, and it moves the photos through the sender's
  phone instead of from the server that already holds them. More parts, no gain here.
- **End-to-end encryption with the key in the link.** The browser's encryption functions
  (WebCrypto) only exist on pages loaded over https or from `localhost`. A phone that opens
  `http://192.168.1.20:8421` has none, so this cannot rescue the unencrypted case, which is
  the only one that would need it; where https exists the transfer is already encrypted. It
  would add code and protect nothing new.
- **Https on the home Wi-Fi** (Caddy with a certificate for a home name, FEATURES 11.1's
  fallback). It would make the Wi-Fi case encrypted, at the price of one more thing to run
  and a name every phone must resolve. Open question 2.
- A link that works several times; choosing the format or size; "save to Photos" on iPhone
  (downloads land in Files); a setting screen for the switches; any new dependency (the QR
  code is drawn by a small encoder in this repository).

## Open questions for C

1. The door for the home Wi-Fi (`PA_SEND_TO_DEVICE_LISTEN`) opens a port on the home
   network. It serves only the receiving page, but it is the first thing of this app that
   listens beyond the server itself. Yes?
2. Should the Wi-Fi case be encrypted one day (Caddy and a home certificate), or is the
   warning enough?
3. Ten minutes, 100 photos, 1 GB, 90 days of trail: right?
4. Closing the dialog cancels the link. Should a link be able to outlive the dialog (copy
   it, close, paste it elsewhere)?

## Failure modes covered by tests

Domain: state one tick before, exactly at and after expiry; collect twice; collect after
cancel; cancel after collect; size limits at and over the boundary; lifetime range;
encrypted or confirmed or refused; an https link never honoured over http.

App and adapter (real SQLite): the token is 256 bits and only its hash is stored; a wrong
token finds nothing; eight threads collect at once and exactly one wins, twenty times; the
limiter per address and overall; rows pruned at 90 days; rows go with their account.

API: off = 404 everywhere, and the page too; guest refused; photos the sender cannot see or
download refused, another person's private photo among them; access taken away between
making and collecting; sender disabled; plain http needs the yes each time, can be switched
off, and an https link opened over http is refused and cancelled; https believed only from
the trusted proxy; one answer for every dead token; headers; the token in no log line; one
file and a ZIP; a stripped copy has no GPS and no camera, is upright, keeps its colour
profile, and the library file's hash is unchanged; the door answers nothing else, listens
for real and stops with the server.

Web: the QR encoder square for square against OpenCV's encoder, and those codes read back
by OpenCV's decoder; the words of the dialog and the trail; the mock's routes; e2e on desktop
and phone against the mock and the real backend.

## As built (2026-10-13)

- The first draft refused plain http outright and kept a test-mode override to exercise
  that. Both are gone with decision 2. What test mode has instead is a way to switch the
  whole feature on for one browser test (`POST /__test/reset {"send": true}`); the reset
  route only exists with `PA_TEST_MODE`, which refuses to start beyond `127.0.0.1`.
- The second door and the "which address" choice were not in the draft; they follow from
  decision 4 and from what is true about the deployment.
- The receiving page is three static files (`web/static/receive.*`), not a route of the app:
  it loads nothing else, and the door can serve them too. It needs JavaScript, because only
  a script can read the part of the link after `#`.
- The page's own `Referrer-Policy` is `same-origin`, not `no-referrer`: with `no-referrer` a
  browser posts the page's form with `Origin: null`, which the cross-site guard refuses. The
  two token routes answer `no-referrer`. Nothing reaches another site either way.
- "One answer for every dead token" won over "a clear state for each" on the receiving page:
  it says "used, ran out or was cancelled". It names the exact state only where it knows it
  without asking: after its own download, and when it watches the time run out.
- Download had a gap that removing details would have inherited: a converted file stripped
  of its metadata also lost its colour profile. Fixed for Download too (`RenderSpec.
  keep_profile`); done by dropping the other fields before saving, because the server's
  libvips (8.14) has no "keep only the profile" option.
- OpenCV's QR encoder leaves one of the seven unused squares of versions 2 to 6 set, where
  the standard has zeros. The reference codes have the standard's zeros there, and OpenCV's
  decoder reads them back.
- Not built from the brief: a "library name" on the receiving page (there is no such
  setting; it shows the sender's display name), and the system share sheet as a fallback
  (the QR code is there).
