"""Generate a realistic *mock* photo library for development, demos and screenshots.

Every image is drawn here (skies, sea, hills, sun, shapes): no real photos, no third-party
content. Metadata is what makes it realistic: ~15 years of dates clustered into events and
trips, GPS for the places, several cameras, rotated portraits, bursts, exact duplicates across
sources, screenshots, and files without EXIF (Facebook-style names).

    uv run python scripts/make_mock_library.py [OUT] [--count 400] [--seed 42]

Writes three source folders under OUT (default: ~/PhotoAssistant/mock-sources):
    phone/     iPhone-style camera roll
    old-hdd/   older camera + GoPro photos, plus duplicates of some phone photos
    partner/   a second person's photos, overlapping some events
"""

import argparse
import math
import random
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import exiftool  # type: ignore[import-untyped]
import pyvips  # type: ignore[import-untyped]


@dataclass(frozen=True)
class Place:
    name: str
    lat: float
    lon: float
    palette: tuple[tuple[int, int, int], tuple[int, int, int]]  # sky, ground


PLACES = [
    Place("Dordogne house", 44.89, 1.22, ((150, 190, 230), (90, 130, 60))),
    Place("Paris", 48.8566, 2.3522, ((170, 180, 200), (120, 110, 100))),
    Place("Brittany coast", 47.75, -3.37, ((120, 170, 220), (40, 90, 140))),
    Place("Montara, California", 37.5427, -122.5164, ((200, 170, 150), (50, 100, 150))),
    Place("Alps", 45.92, 6.87, ((110, 160, 230), (235, 240, 245))),
    Place("Lisbon", 38.7223, -9.1393, ((230, 190, 140), (200, 120, 80))),
]

CAMERAS = {
    "phone": [("Apple", "iPhone 8"), ("Apple", "iPhone 12"), ("Apple", "iPhone 15")],
    "old-hdd": [("Canon", "Canon EOS 600D"), ("GoPro", "HERO4 Silver")],
    "partner": [("Apple", "iPhone 13 mini")],
}


@dataclass(frozen=True)
class Event:
    place: Place
    start: datetime
    days: int
    photos: int


def plan_events(rng: random.Random, count: int) -> list[Event]:
    events = []
    for year in range(2012, 2027):
        events.append(Event(PLACES[0], datetime(year, 12, 24, 10), 3, 8))  # Christmas at home
        events.append(Event(PLACES[0], datetime(year, 6, 1, 9), 60, 10))  # summer at home
        trip = rng.choice(PLACES[1:])
        month = rng.choice([4, 5, 7, 8, 9, 10])
        events.append(Event(trip, datetime(year, month, rng.randint(1, 20), 9), 6, 12))
    scale = count / sum(e.photos for e in events)
    return [Event(e.place, e.start, e.days, max(1, round(e.photos * scale))) for e in events]


def scene(rng: random.Random, place: Place, when: datetime, w: int, h: int) -> pyvips.Image:
    """A simple landscape: sky gradient, ground, sun/moon, a few soft shapes."""
    sky, ground = place.palette
    dusk = 1.0 - min(1.0, abs(when.hour - 13) / 9)
    sky_at_this_hour = [int(c * (0.55 + 0.45 * dusk)) for c in sky]
    y = pyvips.Image.xyz(w, h)[1]
    t = y / h
    sky_img = (t * -60 + sky_at_this_hour).cast("uchar")  # darker towards the horizon
    horizon = int(h * rng.uniform(0.5, 0.7))
    ground_img = (pyvips.Image.black(w, h, bands=3) + list(ground)).cast("uchar")
    mask = (y > horizon + (pyvips.Image.xyz(w, h)[0] / w * math.pi * 4).sin() * 12).ifthenelse(
        255, 0
    )
    img = mask.ifthenelse(ground_img, sky_img)
    sun_x, sun_y, r = rng.randint(w // 8, w * 7 // 8), rng.randint(h // 10, horizon // 2), h // 12
    img = img.draw_circle([255, 240, 200], sun_x, sun_y, r, fill=True)
    for _ in range(rng.randint(2, 6)):
        colour = [rng.randint(30, 230) for _ in range(3)]
        x, yy = rng.randint(0, w), rng.randint(horizon, h)
        img = img.draw_circle(colour, x, yy, rng.randint(h // 30, h // 10), fill=True)
    return img.gaussblur(1.2).cast("uchar").copy(interpretation="srgb")


def screenshot(rng: random.Random, w: int, h: int) -> pyvips.Image:
    img = (pyvips.Image.black(w, h, bands=3) + [245, 245, 245]).cast("uchar")  # noqa: RUF005
    y = 40
    while y < h - 40:
        width = rng.randint(w // 3, w - 80)
        img = img.draw_rect([60, 60, 60], 40, y, width, 14, fill=True)
        y += rng.randint(28, 60)
    return img.copy(interpretation="srgb")


def exif_tags(
    rng: random.Random, when: datetime, camera: tuple[str, str], place: Place
) -> dict[str, object]:
    make, model = camera
    tags: dict[str, object] = {
        "EXIF:DateTimeOriginal": when.strftime("%Y:%m:%d %H:%M:%S"),
        "EXIF:OffsetTimeOriginal": "+02:00" if 4 <= when.month <= 10 else "+01:00",
        "EXIF:Make": make,
        "EXIF:Model": model,
    }
    if rng.random() < 0.25:
        tags["EXIF:Orientation#"] = 6  # portrait
    if rng.random() < 0.85:
        lat = place.lat + rng.uniform(-0.02, 0.02)
        lon = place.lon + rng.uniform(-0.02, 0.02)
        tags["GPS:GPSLatitude"] = abs(lat)
        tags["GPS:GPSLatitudeRef"] = "N" if lat >= 0 else "S"
        tags["GPS:GPSLongitude"] = abs(lon)
        tags["GPS:GPSLongitudeRef"] = "E" if lon >= 0 else "W"
    return tags


def shot_times(rng: random.Random, event: Event) -> list[datetime]:
    """Capture times for one event; a few bursts of five frames one second apart."""
    times: list[datetime] = []
    while len(times) < event.photos:
        when = event.start + timedelta(
            days=rng.randrange(event.days), hours=rng.randint(0, 10), minutes=rng.randint(0, 59)
        )
        frames = 5 if rng.random() < 0.06 else 1
        times.extend(when + timedelta(seconds=i) for i in range(frames))
    return times[: event.photos]


def write_event(
    rng: random.Random, tool: exiftool.ExifToolHelper, out: Path, event: Event, size: int, n: int
) -> int:
    folder = rng.choices(list(CAMERAS), weights=[6, 2, 2])[0]
    camera = rng.choice(CAMERAS[folder])
    for when in shot_times(rng, event):
        image = scene(rng, event.place, when, size, size * 3 // 4)
        prefix = "DSC_" if folder == "old-hdd" else "IMG_"
        path = out / folder / str(when.year) / f"{prefix}{n + 1000:05d}.JPG"
        path.parent.mkdir(parents=True, exist_ok=True)
        image.jpegsave(str(path), Q=72, strip=True)
        tool.set_tags(
            [str(path)],
            exif_tags(rng, when, camera, event.place),
            params=["-overwrite_original", "-q"],
        )
        n += 1
        if rng.random() < 0.05:  # a Facebook download: no EXIF, id-style name
            fb_id = f"{rng.randint(10**7, 10**8)}_{rng.randint(10**14, 10**15)}_n.jpg"
            image.jpegsave(str(out / folder / fb_id), Q=60, strip=True)
            n += 1
    return n


def write_screenshots(rng: random.Random, out: Path, count: int) -> int:
    for i in range(count):
        when = datetime(2020 + i % 7, 1 + i % 12, 1 + i % 27, 12, i % 60, 0)
        shot = out / "phone" / "Screenshots" / f"Screenshot_{when:%Y%m%d-%H%M%S}.png"
        shot.parent.mkdir(parents=True, exist_ok=True)
        screenshot(rng, 750, 1334).pngsave(str(shot))
    return count


def write_duplicates(rng: random.Random, out: Path, count: int) -> int:
    """Old backups of phone photos on the HDD, and a few the partner kept too."""
    phone = sorted((out / "phone").rglob("IMG_*.JPG"))
    backups = rng.sample(phone, k=min(len(phone), count // 20))
    shared = rng.sample(phone, k=min(len(phone), count // 40))
    for src in backups:
        shutil.copy2(src, out / "old-hdd" / f"backup-{src.name}")
    for src in shared:
        shutil.copy2(src, out / "partner" / f"from-C-{src.name}")
    return len(backups) + len(shared)


def main() -> None:
    parser = argparse.ArgumentParser()
    default_out = Path.home() / "PhotoAssistant" / "mock-sources"
    parser.add_argument("out", nargs="?", default=str(default_out))
    parser.add_argument("--count", type=int, default=400)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--size", type=int, default=1600, help="long edge in pixels")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    out = Path(args.out).expanduser()
    if out.exists():
        shutil.rmtree(out)
    for folder in CAMERAS:
        (out / folder).mkdir(parents=True)

    written = 0
    with exiftool.ExifToolHelper() as tool:
        for event in plan_events(rng, args.count):
            written = write_event(rng, tool, out, event, args.size, written)
    written += write_screenshots(rng, out, max(3, args.count // 40))
    written += write_duplicates(rng, out, args.count)
    for leftover in out.rglob("*_original"):
        leftover.unlink()
    print(f"wrote {written} mock files to {out}")


if __name__ == "__main__":
    main()
