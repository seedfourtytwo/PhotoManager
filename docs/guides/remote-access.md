# Remote access with Tailscale (phone, laptop away from home)

Tailscale makes a private network between your own devices. The app is reachable from your
phone anywhere, with HTTPS, and from nobody else. Free for personal use.

**Never expose the app to the public internet** (no port forwarding on the router, no public
Funnel): it holds the whole family's photos, and even with login every public endpoint gets
probed by bots all day. Tailscale keeps it invisible.

## 1. Install Tailscale

On the machine running the app (laptop now, server later):

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

On the iPhone: install Tailscale from the App Store and sign in with the same account.

## 2. Turn on MagicDNS and HTTPS (once, in the admin console)

<https://login.tailscale.com/admin/dns>: enable **MagicDNS** and **HTTPS Certificates**.
Your machines now have names like `server.tail1234.ts.net`. Rename the machine to `photos`
in the Machines list if you like: `photos.tail1234.ts.net`.

## 3. Serve the app over HTTPS

The app keeps listening on 127.0.0.1; Tailscale terminates HTTPS and forwards to it:

```bash
sudo tailscale serve --bg --https=443 http://127.0.0.1:8420
tailscale serve status
```

This fetches and renews the certificate itself (`tailscale cert` is only needed if you
terminate HTTPS somewhere else, e.g. Caddy).

The app must listen on 127.0.0.1 for this (`PA_HOST`, the default). Tailscale then reaches it
from 127.0.0.1, the one address the app believes when it says a request came over HTTPS
(`PA_TRUSTED_PROXIES`); it sends `X-Forwarded-Proto: https` and keeps the host name. If you
made the app listen on the home network's address so phones could use plain http, set
`PA_HOST=127.0.0.1` again (or forward to that address and add it to `PA_TRUSTED_PROXIES`):
otherwise the app takes the HTTPS page for another site and refuses the sign-in.

## 4. Tell the app its name

The app refuses requests for host names it doesn't know (protection against DNS
rebinding). Add the Tailscale name:

- laptop, in `.env`: `PA_ALLOWED_HOSTS=127.0.0.1,localhost,photos.tail1234.ts.net`
  then `systemctl --user restart photo-assistant`
- server with Docker, in `deploy/server.env`: same line, then
  `docker compose -f deploy/compose.yml up -d`

Write the names separated by commas, with no quotes, brackets or spaces: that form is read the
same way by `just run`, the systemd service and Docker.

## 5. Use it

Open `https://photos.tail1234.ts.net` on the phone (Tailscale app connected), then put it on
the Home Screen (below) so it opens full screen.

## On the Home Screen: full screen, like an app

A page in a browser tab can't hide the browser's bars. Added to the Home Screen and opened
from its icon, it can. On a phone in a browser tab the app shows a one-time tip saying how.

- **iPhone** (iOS 26 or later), in Safari: tap ⋯ (the page menu), then Share, then scroll to
  Add to Home Screen (missing? Edit Actions at the bottom of the list adds it). Keep **Open as
  Web App** on and tap Add. With the Bottom or Top tab layout, Share is in the bar itself. In
  another iPhone browser: Share → Add to Home Screen.
- **Android**, in Chrome: the tip's Install button, or Chrome's menu → Install app.

What plain http (e.g. `http://192.168.1.183:8420`) gives, against HTTPS:

|                                          | plain http                                                                  | HTTPS (`tailscale serve`) |
| ---------------------------------------- | --------------------------------------------------------------------------- | ------------------------- |
| iPhone: full screen from the Home Screen | yes: iOS 26 opens every site added as an app, and Apple names no HTTPS rule | yes                       |
| Android: install, full screen            | no: a shortcut that opens in Chrome                                         | yes                       |
| Share sheet (AirDrop, Quick Share)       | no                                                                          | yes                       |
| Opens with no network (service worker)   | no                                                                          | yes                       |
| Away from home                           | no                                                                          | yes (Tailscale)           |

An icon keeps the address it was added from. After moving to HTTPS, delete the http icon and
add the app again from the `https://` address. The new icon may ask for the PIN once.

The page runs under the clock and the home bar and keeps everything you read or press clear
of them. iOS writes the clock in white over it (`black-translucent`), which suits the dark
look; in the light look the clock is hard to read, and iOS has no setting that picks the
colour by itself. Since iOS 26.1 some iPhones show a plain strip behind the clock instead
([WebKit bug 301994](https://bugs.webkit.org/show_bug.cgi?id=301994), open); nothing hides
then either.

Sources (October 2026):
[WebKit: Safari 26.0](https://webkit.org/blog/17333/webkit-features-in-safari-26-0/)
("every website added to the Home Screen opens as a web app", "zero requirements for
installability") ·
[Apple: Turn a website into an app](https://support.apple.com/guide/iphone/open-as-web-app-iphea86e5236/ios) ·
[web.dev: install criteria](https://web.dev/articles/install-criteria) (served over HTTPS) ·
[web.dev: installation](https://web.dev/learn/pwa/installation) (otherwise a shortcut) ·
[MDN: service workers](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API)
and [secure contexts](https://w3c.github.io/webappsec-secure-contexts/) (a LAN address is not
one) ·
[Apple: supported meta tags](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/SafariHTMLRef/Articles/MetaTags.html)
(status bar style) ·
[WebKit bug 210597](https://bugs.webkit.org/show_bug.cgi?id=210597) (the white clock).

## What the PIN does and does not protect

The sign-in is a 4-digit PIN, sized for a family behind Tailscale, not for the internet. Ten
wrong PINs make the account wait 15 minutes; thirty since its last good sign-in lock it until
an admin unlocks it or gives it a new PIN (`just set-pin <name>` on the server). Guessing a
PIN therefore fails, but anyone who can reach the sign-in page can lock any account on
purpose, since the page lists every account name. That is accepted while only your own
devices reach the app; it is one more reason never to forward a port to it.

The app speaks plain http and relies on Tailscale for HTTPS. Opening it by the machine's
LAN address over http (`PA_HOST` set to that address) sends the PIN and the session cookie
unencrypted across the home network: fine on a network you trust, not on a shared one.

## Checklist

- [ ] `tailscale serve status` shows `https://…ts.net → http://127.0.0.1:8420`
- [ ] the router has **no** port forward for 8420/443
- [ ] `PA_HOST` is `127.0.0.1` for the systemd service; with Docker the port is published on
      `127.0.0.1` only (`deploy/compose.yml`)
- [ ] login is enabled (M2) before anyone else's phone joins the tailnet
