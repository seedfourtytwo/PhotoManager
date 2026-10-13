# Send to a device: a one-time link for chosen photos

Date: 2026-10-13. Area: `handover` (domain, app, adapters, api), the web app (a dialog, a
receiving page, a small QR drawer), docs. Off by default; C decides whether it is ever turned on.

## Goal

C or his partner picks photos, the app shows a QR code and a link, another device opens it
and downloads those photos straight from the home server. The other device needs no account.
The link works once, for ten minutes, and only over https.

The phone's own share sheet (AirDrop, Quick Share) is a separate piece of work (`feat/share`).
This is the app's own way, for when the other device is not next to you or is not an Apple or
Android phone.

## What is true today (and limits who can use this)

- The app listens on `127.0.0.1:8420` in plain http. The only https address is the one
  `tailscale serve` puts in front of it: `https://<machine>.<tailnet>.ts.net`.
- That address is reachable only from devices signed in to C's Tailscale network (or a
  machine C has shared with one). A visitor's phone on the home Wi-Fi without Tailscale
  cannot reach the app at all, with or without this feature.
- The app already knows whether a request arrived over https: uvicorn believes the
  `X-Forwarded-Proto` header only from the addresses in `PA_TRUSTED_PROXIES` (default: this
  machine, where `tailscale serve` runs). The session cookie's `Secure` flag relies on the
  same fact. A request that reaches the port directly cannot claim https.

So, as built: **the receiving device must be on the tailnet.** That covers C's and his
partner's own phones, tablets and laptops. It does not cover a guest on the Wi-Fi. Reaching
guests needs a second https address on the home network, which is an open question below.

## The flow

Sender (signed in, member or admin):
1. Selects photos (or opens one) → More → **Send to a device**.
2. A dialog shows a QR code, the link with Copy, "3 photos · 8.4 MB", a countdown, and
   "Waiting…".
3. When the other device has taken them the dialog says "Downloaded on another device".
   Closing the dialog while it still waits cancels the link.

Receiver (no account):
1. Scans the QR code or opens the link. A small page says "C is sending you 3 photos" and has
   one button, **Download**.
2. The tap downloads one photo, or a ZIP of several. The link is now used up.
3. A link that no longer works says so in one sentence.

## Design

### The hand-over (pure rules, `domain/handover.py`)

A hand-over is a fixed list of photo ids, who made it, when it runs out, how often it may be
collected (1), and when it was collected or cancelled. Its state is worked out, never stored:
`waiting`, `redeemed`, `expired`, `cancelled`.

- Runs out after 10 minutes (`PA_SEND_TO_DEVICE_MINUTES`, 1 to 60). At exactly the expiry
  time it is expired.
- At most 100 photos and about 1 GB per hand-over.
- Only a waiting hand-over can be cancelled or collected.

### The token and the link

- 256 random bits from the operating system, URL-safe text. Only its SHA-256 is stored, as
  for sessions and device tokens. Shown once, to the sender.
- The link is `https://<the address the sender is using>/receive.html#<token>`. The token
  sits after the `#`: browsers never send that part to a server, so it is in no access log,
  no proxy log and no `Referer`. The receiving page reads it and sends it in the body of a
  POST.
- Because of that, a link preview (a chat app fetching the link) or a QR scanner's prefetch
  gets a page with no token in it and cannot use the link up. The photos leave only on the
  tap, which makes the POST.

### Who may send what

Members and admins, not guests. Every photo must be visible to the sender through the
existing access rule and at download level; another person's private photos therefore never
qualify. The same check runs again when the link is collected, as the sender: a photo the
sender lost access to meanwhile is left out, and a sender whose account was disabled sends
nothing.

### Encrypted in transit, enforced

"Encrypted" means: the photos travel inside https (TLS) between the home server's Tailscale
proxy and the receiving browser, and inside Tailscale's own encryption underneath. It holds
whenever the link is created and collected through the https address. The app refuses both
steps on anything else: creating a link over plain http is refused with a sentence that says
to open the library at its https address; a token that arrives over plain http is refused
and its hand-over is cancelled, because the token has just crossed the network in the clear.

It is not end-to-end encryption: the home server reads the photos (it holds them anyway).

### The receiving side (no session, so guarded differently)

- `POST /api/handovers/look` says how many photos and from whom; `POST
  /api/handovers/collect` sends them and uses the link up. Both take the token in the body.
- One answer for a wrong, used, expired or cancelled token, so nobody can probe which is
  which. The page turns it into one sentence.
- Wrong tokens are counted per address (10 in 15 minutes) and overall (100 in 15 minutes),
  then refused with "wait"; the same idea as the PIN limit, kept in memory.
- Collecting is one atomic database update: of two taps at the same moment, one gets the
  photos.
- Photos are sent as full-size JPEGs with the sender's edits (the Download dialog's "With
  edits" choice), so any phone opens them; one photo as a file, several as a streamed ZIP
  with Download's file names.
- `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, and the page may only load its
  own script and talk to its own server.

### Storage and the trail

One new table, `handover`. Its rows are also the record C can read: who sent how many
photos, when, whether and when they were collected and from which address. Members see their
own in Settings, admins see everyone's, and a waiting one has Cancel. Rows are deleted after
90 days by the daily clean-up that already prunes the AI log.

### The switch

`PA_SEND_TO_DEVICE` (default `false`). While off, every route answers 404 as an unknown
address does and the web app shows nothing.

## Threat model, in plain words

| Someone… | What happens |
|---|---|
| sees the QR code over your shoulder and scans it first | They get the photos, if their device is on the tailnet. The sender's dialog then says "Downloaded" before the intended person tapped: that is the warning sign. One use limits it to those photos, once. |
| gets the link forwarded in a chat | Same as above: whoever opens it first, within 10 minutes, on the tailnet, gets the photos. The chat app's own preview cannot use it up. |
| replays the link later | Refused: used, expired or cancelled all read "does not work any more". |
| guesses tokens | 256 bits cannot be guessed; the counter stops the trying anyway. |
| reads the server's or the proxy's logs | The token is not in them (it is never part of an address). The trail holds only its hash. |
| listens on the Wi-Fi | Sees Tailscale's encrypted traffic, nothing else. The app refuses to do this over plain http. |
| steals the receiving phone | Has the downloaded photos, like any file on that phone. The link in its history is used up. |
| steals the sender's unlocked, signed-in phone | Can send photos to themselves, as they could already download them. |
| runs a program on the home server itself | Can claim "this was https" to the app. Same trust the sign-in cookie already places in the server. |

What stays true whatever is done: the photos are only as private as the device that
received them, and files carry their location and camera details like any download.

## Deliberately not built

- **Browser-to-browser transfer (WebRTC).** It needs a signalling server and often a relay,
  both devices awake in a browser at once, and it moves the photos through the sender's
  phone instead of from the server that already holds them. More parts, no gain here.
- **End-to-end encryption with the key in the link.** The browser's encryption functions
  (WebCrypto) only exist on pages loaded over https. So it cannot rescue a plain-http
  network; and where https exists the transfer is already encrypted, and the server holds
  the photos unencrypted anyway. It would add code and protect nothing new.
- A link that works several times or for several people; choosing the format or size;
  stripping location; a "save to Photos" button on iPhone (downloads go to Files).
- An https address for the home Wi-Fi, a setting screen for the switch (it is an
  environment variable like every other setting), and any new dependency: the QR code is
  drawn by a small encoder in this repository.

## Open questions for C

1. Is a link that needs no account acceptable at all? If not, this stays off or is removed.
2. Guests on the Wi-Fi cannot use it today. Options: leave it (tailnet devices only); add
   Caddy with a certificate for a home name (the FEATURES 11.1 fallback: more to run, and the
   app would then listen on the home network); or Tailscale Funnel (public internet, which
   remote-access.md rules out). Recommendation: leave it.
3. Ten minutes, single use, 100 photos, 1 GB: right?
4. Should sent files keep their location, as downloads do, or lose it by default?
5. Keep the trail for 90 days?

## Failure modes covered by tests

Domain: state at each boundary (one second before, exactly at, after expiry); collect twice;
collect after cancel; cancel after collect; size limits at and over the boundary; lifetime
range.

App and adapter: token is 256 bits and only its hash is stored; a wrong token finds nothing;
two threads collect at once and exactly one wins; the limiter per address and overall; old
rows are pruned.

API: off = 404 everywhere; guest refused; photos the sender cannot see or download refused;
private photos of another person refused; access revoked between create and collect; plain
http refused for create, look and collect, and it cancels the hand-over; https believed only
from a trusted proxy; uniform refusals; headers; the token in no log line; one file and a ZIP.

Web: the QR encoder against vectors from an independent encoder; dialog states; the
receiving page; e2e on desktop and phone against the mock and the real backend.
