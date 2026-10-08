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

Open `https://photos.tail1234.ts.net` on the phone (Tailscale app connected). In Safari:
Share → Add to Home Screen for the full-screen app.

## Checklist

- [ ] `tailscale serve status` shows `https://…ts.net → http://127.0.0.1:8420`
- [ ] the router has **no** port forward for 8420/443
- [ ] `PA_HOST` is `127.0.0.1` for the systemd service; with Docker the port is published on
      `127.0.0.1` only (`deploy/compose.yml`)
- [ ] login is enabled (M2) before anyone else's phone joins the tailnet
