# Send to a device (a one-time link and QR code)

Pick photos, show a QR code, and another device downloads them straight from the library:
no account, no app, any phone browser. The link works **once**, for **ten minutes**.

It is **off** until you switch it on. Read "What it does not protect against" first: a link
that needs no account is a deliberate hole in "nobody gets in without signing in".

## What it does

- Select photos (or open one) → **More** → **Send to a device**.
- Choose whether to **remove details** (on by default: the copies then carry no location, no
  camera details and no file names; the photos in the library are never changed).
- The dialog shows a QR code and a link, counts down, and says when the photos were
  downloaded. Closing it while it still waits cancels the link.
- The other device opens the link, sees "C is sending you 3 photos" and one button. The
  photos arrive as JPEGs: one as a file, several as a ZIP.
- **Settings → Sent to a device** lists what was sent in the last 90 days: how many photos,
  when, whether and from which address they were downloaded. A waiting link has Cancel. You
  see your own; an admin sees everyone's.

Members and admins can send, guests cannot. Only photos the sender may download can be sent,
and that is checked again at the moment they are collected.

## Turn it on

In `.env` (laptop) or `deploy/server.env` (Docker), then restart the app:

```
PA_SEND_TO_DEVICE=true
```

That alone is enough for **devices on your Tailscale network**: the link uses the address
you are browsing at (`https://photos.tail1234.ts.net`), and it is encrypted.

## A phone on the home Wi-Fi, without Tailscale

The library only listens on the server itself (`127.0.0.1`); a phone on the Wi-Fi cannot
reach it. Do **not** change `PA_HOST` to fix that: it would put the sign-in screen, and every
PIN typed into it, on the Wi-Fi in clear text.

Instead open a second, small door that serves only the receiving page:

```
PA_SEND_TO_DEVICE_LISTEN=0.0.0.0:8421
PA_SEND_TO_DEVICE_ADDRESS=http://192.168.1.20:8421
```

- `PA_SEND_TO_DEVICE_LISTEN`: where the door listens. `0.0.0.0` means every network the
  server is on; write the server's own Wi-Fi address instead (`192.168.1.20:8421`) to keep it
  to that one.
- `PA_SEND_TO_DEVICE_ADDRESS`: what goes into the QR code. It must be the address a phone on
  the Wi-Fi types to reach that door: the server's address on the home network (`hostname -I`
  on the server shows it) and the door's port. Give the server a fixed address in the router,
  or this stops working when it changes.
- With Docker, publish the door's port in `deploy/compose.yml` (`"8421:8421"`), and only that
  one. Port 8420 stays on `127.0.0.1`.
- A firewall on the server must let port 8421 in from the home network.

The door answers the receiving page and its two requests. Everything else (the library, the
sign-in, every other address) is a 404 there. It speaks plain http: there is no certificate
for a home address.

Because of that, such a link is **not encrypted**. Each time, the dialog warns the sender
("Anyone on the same network could see these photos while they travel…") and needs a tap on
**Send anyway**; the receiving page says so too, and so does the list in Settings. When the
sender is on the Tailscale address and a home address is set, the dialog asks where the
other device is and starts on the encrypted one.

To forbid unencrypted links altogether: `PA_SEND_TO_DEVICE_UNENCRYPTED=false`.

## Settings

| Variable | Default | |
|---|---|---|
| `PA_SEND_TO_DEVICE` | `false` | The switch. Off: nothing shows, every address of the feature is a 404. |
| `PA_SEND_TO_DEVICE_MINUTES` | `10` | How long a link works (1 to 60). |
| `PA_SEND_TO_DEVICE_UNENCRYPTED` | `true` | `false`: only https links can be made. |
| `PA_SEND_TO_DEVICE_REMOVE_DETAILS` | `true` | What "Remove details before sending" starts as. |
| `PA_SEND_TO_DEVICE_ADDRESS` | not set | The address for phones on the home Wi-Fi (goes into the QR code). |
| `PA_SEND_TO_DEVICE_LISTEN` | not set | The second door for that address. |

## How the app knows a link is encrypted

It does not trust the browser. `tailscale serve` tells the app "this came in over https" in
a header, and the app believes that header only from the addresses in `PA_TRUSTED_PROXIES`
(by default the server itself). The second door has nothing in front of it, so there it is
never https. If the app cannot tell, it treats the link as not encrypted and warns.

## What it protects against

- **Guessing.** The link holds 256 random bits; wrong tries are counted and cut off.
- **Using it twice, or later.** One download, ten minutes, then it is dead. Used, expired and
  cancelled links all give the same answer.
- **Logs.** The secret part of the link comes after `#`, which browsers never send to a
  server: it is in no access log. The library stores only its fingerprint.
- **Link previews.** A chat app that fetches the link to show a preview gets a page with no
  secret in it and cannot use the link up; the photos leave only when a person taps Download.
- **A listener on the network**, when the link is https. Not when it is not: see below.

## What it does not protect against

- **Whoever opens the link first gets the photos.** Someone who photographs the QR code over
  your shoulder, or gets the link forwarded, and is on the same network, can be that person.
  The sign: the dialog says "Downloaded" before the person you meant has tapped.
- **An unencrypted link on the Wi-Fi**: anyone on that Wi-Fi who records traffic can copy the
  photos while they travel, and could even use the link before the intended phone does.
  Use it for what you would not mind them seeing.
- **The receiving device.** Once downloaded, the photos are as private as that phone.
- **Details you chose to keep.** With "Remove details" off, the files carry where and when
  they were taken.
- On an iPhone the download lands in the Files app, not in Photos.

## Check it works

1. Sign in, select a photo, More → Send to a device. No such entry: the switch is off, the
   app was not restarted, or you are signed in as a guest.
2. "Other devices cannot open the address you are using": you are browsing at `localhost`
   and no home address is set.
3. Scan the code with a phone. "Could not be reached": the phone is not on the network the
   address belongs to, the door is not listening (`ss -ltn | grep 8421`), or a firewall is in
   the way.
