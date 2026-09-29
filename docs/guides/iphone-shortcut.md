# Automatic iPhone upload with Apple Shortcuts (free)

This sets up your iPhone to send new photos to Photo Assistant on its own — for example every
time you plug it in to charge. It uses the **Shortcuts** app that comes with every iPhone:
nothing to buy, nothing to install from the App Store.

It takes about 10 minutes. You do it once per iPhone.

## What you need

- Photo Assistant running on the laptop or home server, reachable from the phone:
  - at home: the phone on the same Wi-Fi, **or**
  - anywhere: the free **Tailscale** app on the phone and on the server, both signed in to the
    same account.
- The server's web address, e.g. `https://photos.your-tailnet.ts.net` (ask whoever set up the
  server; it must be one of the addresses Photo Assistant accepts).
- A **device token** for this phone (next section).

## 1. Get a device token for this phone

A device token is a long password just for this phone. It can only upload photos; it can't see
or delete anything. You can switch it off at any time.

1. In Photo Assistant (in a browser, signed in as yourself), open **Settings → Phones &
   devices → Add a device**.
2. Name it (e.g. "Léa's iPhone"), choose iPhone, and press **Create**.
3. The token (it starts with `pa_dev_`) is shown **once**. Copy it — easiest is to open this
   page on the iPhone itself and tap Copy. If you lose it, just revoke the device and create a
   new one.

## 2. Build the automation

Open the **Shortcuts** app → tab **Automation** at the bottom → **+** (top right, or
"New Automation").

### Choose when it runs

- Pick **Charger** → **Is Connected** (runs when you plug in the phone), or
  **Time of Day** → e.g. 03:00, Daily.
- Choose **Run Immediately** (not "Run After Confirmation") and switch **Notify When Run** off.
  Tap **Next**, then **New Blank Automation**.

### Add the actions (tap "Add Action" and search for each name)

1. **Find Photos**
   - Tap "Add Filter": **Date Added** · **is in the last** · **2** · **days**.
     (On some iOS versions the filter is called *Creation Date*; that works too.)
   - Add a second filter: **Media Type** · **is** · **Image** (videos aren't accepted yet).
   - Turn on **Limit** and set **Get 50 Photos**.
2. **Repeat with Each** — it should say "Repeat with each item in *Photos*".
3. Inside the repeat, add **Get Contents of URL**:
   - URL: `https://<your server address>/api/upload`
   - Tap the arrow **>** to show more options:
     - **Method:** POST
     - **Headers:** Add new header → Key `Authorization`, Text `Bearer ` followed by your
       token (one space after the word Bearer), e.g. `Bearer pa_dev_Xy12…`
     - **Request Body:** Form
     - Add new field → type **File** → Key `file` → Value: tap and choose
       **Repeat Item**.
4. Make sure the **End Repeat** comes after "Get Contents of URL".

Tap **Done**.

## 3. Test it once

Open the automation and tap the play button ▶ at the bottom (or plug in the phone). After a
minute, the photos from the last two days appear in Photo Assistant under **Uploads**.
Running it again is harmless: photos the library already has are skipped.

## Good to know (the limits)

- **Batch size.** iOS stops automations that run too long or use too much memory, so each run
  sends at most 50 photos. Running on every charge catches up over a few days. After a big
  holiday, run it by hand a few times, or upload from the Photo Assistant web page instead.
- **Two days, not one.** "Last 2 days" overlaps the previous run on purpose, so nothing is
  missed if a run is cut short. Photos already in the library are skipped by the server (they
  are still sent, so it uses some Wi-Fi data).
- **It needs the server to be reachable.** At home on Wi-Fi, or with Tailscale switched on.
  If the server is off or out of reach, that run simply fails; the next one catches up.
- **HEIC stays HEIC.** iPhone photos are usually HEIC files. They're sent as they are, and
  Photo Assistant handles them. Nothing is converted or shrunk.
- **Live Photos:** only the still photo is sent, not the short video.
- **Edited photos:** the edited version is sent. The original iPhone edit history isn't.
- **Storage on the phone isn't freed.** This copies photos; it never deletes anything on the
  phone.
- If you see "device token not valid", the token was revoked or mistyped: create a new one
  (step 1) and paste it into the Authorization header.

## Switching it off

- On the phone: Shortcuts → Automation → swipe left on it → Delete (or open it and turn it
  off).
- In Photo Assistant: **Settings → Phones & devices → Revoke** next to the phone. From that
  moment its token no longer works.

---

### For whoever runs the server (until the Devices screen exists)

Create a token with the API while signed in (browser session cookie):

```
curl -X POST https://<server>/api/devices \
     -H 'Content-Type: application/json' \
     --cookie 'pa_session=<your session cookie>' \
     -d '{"name": "Léa'"'"'s iPhone", "platform": "ios"}'
```

The response contains `"token": "pa_dev_…"` — shown only this once. List devices with
`GET /api/devices`, revoke with `DELETE /api/devices/<id>`.
