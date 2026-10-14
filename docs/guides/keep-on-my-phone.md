# Keep photos on my phone (Apple Shortcuts, free)

> **Not tried on a real iPhone yet.** The server side is built and tested; these Shortcut steps
> are written from Apple's documentation and have not been followed on an iPhone. When C has
> tried them, this note goes and the steps get fixed where they were wrong.

This puts photos from Photo Assistant **onto** your phone, on their own: for example every time
you plug the phone in to charge. You choose what: an album, a person, a search, or the
library's filters (for example "2019 · France"), and you can leave things out (for example
screenshots). It uses the **Shortcuts** app that comes with every iPhone: nothing to buy,
nothing to install.

It takes about 15 minutes, once per phone.

## Good to know first

- **One way only: from Photo Assistant to the phone.** Deleting a photo on the phone does
  **not** delete it in Photo Assistant. Taking an album off the phone's list does **not**
  delete its photos from the phone either: you delete them on the phone yourself.
- A photo counts as on the phone once the shortcut says it saved it (the last step inside the
  repeat). If a run is cut short before that, the photo is simply offered again next time. If
  it was in fact saved, you may get it twice; that is harmless, and an app could tell a repeat
  by the `hash` Photo Assistant sends with each photo.
- A photo you deleted on the phone does not come back by itself. If you want everything again
  (a new phone, a reset), press **Send everything again** in Settings.
- Only photos **you** may download go to your phone. A photo you can only look at (for example
  one that is only in an album someone shared with you) stays on the server. The Keep on phone
  window and Settings say so: "12 photos in this album can't go to your phone: you can only
  view them". Ask whoever set up the library to let you download from the folder they come from.
- Photos you hid, and photos in the trash, never go.
- The photo is the untouched original (an iPhone photo stays HEIC). Edits made in Photo
  Assistant are not applied to it.
- It only works where the phone can reach the server: at home on Wi-Fi, or with Tailscale
  switched on. Nothing is put on the internet for it.

## 1. A device token for this phone

If this phone already uploads with the "Automatic iPhone upload" shortcut, it has one: use the
same token. Otherwise:

1. In Photo Assistant (in a browser, signed in as yourself) open **Settings → Phones and
   devices → Add a device**.
2. Name it (e.g. "Léa's iPhone"), choose iPhone, press **Create**.
3. Copy the token (it starts with `pa_dev_`). It is shown only once.

## 2. Choose what the phone keeps

- On an **album**, a **person**, a **search** or the **Library** with filters chosen, press
  **Keep on phone**. For each phone choose **Keep on it**, **Leave off it** or **Not chosen**.
  "Leave off" wins over "Keep": keep an album but leave off a person, and that person's photos
  in the album stay off the phone.
- **Settings → Phones and devices** shows, under each phone, what it keeps and leaves off, how
  many photos that is and how big, and when the phone last asked. **Leave out screenshots** is
  a tick box there (it needs the photo analysis to be set up; until then it leaves out
  nothing).

## 3. Make an album on the phone

Open **Photos** → Albums → **+** → New Album → call it **Family**. The shortcut puts the
photos there (they are also in Recents, like any saved photo).

## 4. Build the automation

Open **Shortcuts** → **Automation** (bottom) → **+** → **Charger** → **Is Connected** →
**Run Immediately** (switch **Notify When Run** off) → **Next** → **New Blank Automation**.

Add these actions (tap "Add Action" and search for each name):

1. **Text** — type your server address, e.g. `https://photos.your-tailnet.ts.net` (no `/` at
   the end).
2. **Set Variable** — name it `Server`; input: *Text*.
3. **Get Contents of URL**
   - URL: tap and insert the variable `Server`, then type
     `/api/sync/manifest?new=true&limit=20`
   - Tap **>** to show more:
     - **Method:** GET
     - **Headers:** add one: Key `Authorization`, Text `Bearer ` and then your token (one
       space after Bearer), e.g. `Bearer pa_dev_Xy12…`
4. **Get Dictionary Value** — Get **Value** for key `items` in *Contents of URL*.
5. **Repeat with Each** — item in *Dictionary Value*.
6. Inside the repeat:
   1. **Get Dictionary Value** — Get **Value** for key `url` in *Repeat Item*.
   2. **Get Contents of URL**
      - URL: the variable `Server`, then *Dictionary Value* right after it (no space).
      - Method GET, and the same **Authorization** header as in step 3.
   3. **Save to Photo Album** — *Contents of URL*, album **Family**.
   4. **Get Dictionary Value** — Get **Value** for key `id` in *Repeat Item*.
   5. **Get Contents of URL** (this tells Photo Assistant the photo is saved, so it is not
      offered again)
      - URL: the variable `Server`, then type `/api/sync/sent`
      - **Method:** POST, the same **Authorization** header as in step 3
      - **Request Body:** JSON → Add new field → type **Array**, key `ids` → inside it add an
        item of type **Number** and choose the *Dictionary Value* from step 4.
7. Make sure **End Repeat** comes after the last "Get Contents of URL".

Tap **Done**.

## 5. Try it once

Open the automation and tap ▶ (or plug the phone in). Up to 20 photos arrive in the Family
album. Each run fetches the next 20 that are new, so a big album arrives over a few charges;
run it by hand a few times to go faster. Settings → Phones and devices then says "last synced"
with the time, and how many are sent.

## When something goes wrong

- **"device token not valid"**: the token was revoked or mistyped. Make a new one (step 1) and
  put it in **both** Authorization headers.
- **Nothing arrives**: check in Settings that the phone keeps something and the count is not 0,
  and that the phone reaches the server (open the server address in Safari).
- **It stops halfway**: iOS stops automations that run too long. The photos already saved stay;
  the next run carries on, and offers again any photo it had not yet said it saved.
- **The same 20 photos come every time**: the last step inside the repeat (telling Photo
  Assistant the photo is saved) is missing or fails. Check its URL, Method POST, the
  Authorization header, and that the `ids` array holds the *Dictionary Value* of `id`.
- **Send everything again** (Settings) offers the whole list again, for a new or reset phone;
  photos already on the phone then arrive twice.

## Switching it off

- On the phone: Shortcuts → Automation → swipe left on it → Delete.
- In Photo Assistant: Settings → Phones and devices → **Revoke**. Its token stops working at
  once (for uploads too).

## Android

There is no ready-made Android setup yet. Anything that can, on a schedule, fetch a web
address with an `Authorization: Bearer <token>` header and save the answer as a file in the
phone's Pictures folder can do the same job: an automation app (several free and open-source
ones exist), or a small script in a terminal app with `curl`. The steps are the same as above:
ask `/api/sync/manifest?new=true&limit=20`, fetch each item's `url` and save it, then post the
saved ids to `/api/sync/sent` as `{"ids": [...]}`. Skip a photo whose `hash` you already have.

## For whoever runs the server

The routes are in `docs/contracts/api-v1.md` ("Keep on my phone"). A phone fetches only what is
on its own list and can only mark photos of that list as saved; it changes nothing in the
library. A revoked token gets nothing. To look at a phone's list by hand:

```
curl -H 'Authorization: Bearer pa_dev_…' 'https://<server>/api/sync/manifest?limit=5'
```
