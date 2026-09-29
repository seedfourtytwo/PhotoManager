# Open questions for C

Answered decisions move into `TECH_DECISIONS.md` with a date.

## Answered (2026-09-29)

- **Build or adopt?** Own app, borrow ideas from Immich/PhotoPrism.
- **Size?** Under 10,000 photos to start.
- **Users?** One shared library, any number of accounts, access granted per source folder and per album.
- **Test data?** Photos already on the laptop/server; phone and cloud come later.
- **Downloads?** Yes: multi-select, whole years etc., format conversion, resize.
- **Editor?** Yes, basic and non-destructive; colour adjustments decided later.
- **Sources?** Multiple folders, local and remote, aggregated into one library.
- **Copy or reference?** Always copy into the library on connect; sources never touched.
- **Backups?** Yes: incremental, scheduled, to local and/or network targets (restic).
- **Web vs app?** Web for everything now; free Apple Shortcuts automation for automatic iPhone
  upload; own phone app parked (Apple fee). Laptop = browser only once the server exists.
- **Library location:** on the laptop for now (`~/PhotoAssistant/data/`), moved to the Ubuntu
  server later; the move must be easy and tested.
- **Backups:** designed now, built in M6.
- **Repo:** private, on C's personal GitHub account.
- **Language:** English only.
- **Faces:** InsightFace (more accurate; private use only).
- **Partner's phone:** iPhone.
- **Money:** no paid tools or services.
- **Where code lives:** GitHub `seedfourtytwo/PhotoManager`; development happens in Claude's
  cloud workspace against that repo.
- **Privacy:** real photos never go to the cloud or GitHub; real-data checks run on the laptop.

## Still open (none block M0/M1)

1. **Disk space:** is there room on the laptop for a full copy of all photos (~30–60 GB) plus ~10 %?
2. **Print lab:** which photo-book service in France do we target? Its spec sets our presets.
3. **Proton Drive:** the rclone backend is beta; if 2FA login fights us, is exporting through
   Proton's own app into a folder acceptable?
4. **Videos:** when do they come in — after M6, or earlier?
5. **Partner's photos via Proton:** Proton's iPhone auto-backup goes to its Photos section,
   which rclone can't read yet. Until that changes: Apple Shortcuts straight to our server
   (free, automatic), or she drops photos into a normal Proton folder by hand? Also: does she
   have a paid Proton plan? The free one is 5 GB, likely too small for a phone library.
6. **Ollama host:** laptop (8 GB VRAM, small models) or wait for the server GPU?
