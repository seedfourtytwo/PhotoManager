/**
 * Suggested albums (v1.13, FEATURES 5.6): events proposed as albums, as the server works them
 * out (backend domain/events.py, app/album_suggestions.py), on the mock library. Nothing is
 * made until Keep; each account's answers are remembered.
 */
import type { AlbumSuggestion } from '../../src/lib/api/types.ts';
import { HttpError, me, noContent, nowIso, ok, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';
import type { MockAlbum, MockAsset, MockUser } from '../types.ts';

const HOUR = 3_600_000;
const SAME_EVENT_GAP = 3 * HOUR;
const SAME_PEOPLE_GAP = 6 * HOUR;
const OVERNIGHT_GAP = 16 * HOUR;
const MOVED_KM = 25;
const AWAY_KM = 30;
const HOME_CELL_DEG = 0.1;
const MIN_PHOTOS = 8;
const MAX_SUGGESTIONS = 6;
const MOSTLY_IN_ALBUMS = 0.5;
const PREVIEW = 4;
const EARTH_RADIUS_KM = 6371;
const MONTHS = [
	'January',
	'February',
	'March',
	'April',
	'May',
	'June',
	'July',
	'August',
	'September',
	'October',
	'November',
	'December'
];
const GONE = 'this suggestion is no longer there; the list may have changed';

type LatLon = [number, number];
const time = (a: MockAsset) => Date.parse(`${a.taken_at}Z`);
const where = (a: MockAsset): LatLon | null => (a.place ? [a.place.lat, a.place.lon] : null);

function distanceKm([lat1, lon1]: LatLon, [lat2, lon2]: LatLon): number {
	const rad = Math.PI / 180;
	const h =
		Math.sin(((lat2 - lat1) * rad) / 2) ** 2 +
		Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(((lon2 - lon1) * rad) / 2) ** 2;
	return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(h));
}

/** The middle of the grid cell holding the most photos (a tie: the one seen first). */
function homeOf(byTime: MockAsset[]): LatLon | null {
	const cells = new Map<string, LatLon[]>();
	for (const a of byTime) {
		const at = where(a);
		if (!at) continue;
		const cell = `${Math.floor(at[0] / HOME_CELL_DEG)},${Math.floor(at[1] / HOME_CELL_DEG)}`;
		cells.set(cell, [...(cells.get(cell) ?? []), at]);
	}
	let most: LatLon[] | null = null;
	for (const points of cells.values()) if (!most || points.length > most.length) most = points;
	if (!most) return null;
	const mean = (i: 0 | 1) => most.reduce((n, p) => n + p[i], 0) / most.length;
	return [mean(0), mean(1)];
}

type Run = { photos: MockAsset[]; at: LatLon | null; people: Set<number> };

function events(byTime: MockAsset[], peopleOn: (a: MockAsset) => Set<number>): MockAsset[][] {
	const home = homeOf(byTime);
	const away = (at: LatLon | null) => !!at && !!home && distanceKm(home, at) > AWAY_KM;
	const runs: Run[] = [];
	for (const a of byTime) {
		const run = runs.at(-1);
		const at = where(a);
		const people = peopleOn(a);
		const goesOn = (r: Run) => {
			const travelling = away(r.at) && away(at);
			if (r.at && at && !travelling && distanceKm(r.at, at) > MOVED_KM) return false;
			const gap = time(a) - time(r.photos.at(-1)!);
			return (
				gap <= SAME_EVENT_GAP ||
				(travelling && gap <= OVERNIGHT_GAP) ||
				(gap <= SAME_PEOPLE_GAP && [...people].some((p) => r.people.has(p)))
			);
		};
		if (run && goesOn(run)) {
			run.photos.push(a);
			run.at = at ?? run.at;
			for (const p of people) run.people.add(p);
		} else runs.push({ photos: [a], at, people: new Set(people) });
	}
	return runs.map((r) => r.photos).filter((photos) => photos.length >= MIN_PHOTOS);
}

/** The one city all its named photos share, else region, else country, else the most seen. */
function placeName(photos: MockAsset[]): string | null {
	const places = photos.flatMap((a) => (a.place ? [a.place.place] : []));
	for (const part of ['city', 'region', 'country'] as const) {
		const names = new Set(places.map((p) => p[part] ?? ''));
		if (names.size === 1 && !names.has('')) return [...names][0];
	}
	const counts = new Map<string, number>();
	for (const p of places) {
		const name = p.city || p.region || p.country;
		if (name) counts.set(name, (counts.get(name) ?? 0) + 1);
	}
	let best: string | null = null;
	for (const [name, n] of counts) if (best === null || n > counts.get(best)!) best = name;
	return best;
}

/** "Saint-Malo · 12 July 2025", "Brittany · July and August 2025". */
function title(photos: MockAsset[]): string {
	const [first, last] = [photos[0].taken_at.slice(0, 10), photos.at(-1)!.taken_at.slice(0, 10)];
	const [y1, m1, d1] = first.split('-').map(Number);
	const [y2, m2] = last.split('-').map(Number);
	const months = (y2 - y1) * 12 + m2 - m1;
	const joiner = months === 1 ? ' and ' : ' to ';
	const when =
		first === last
			? `${d1} ${MONTHS[m1 - 1]} ${y1}`
			: months === 0
				? `${MONTHS[m2 - 1]} ${y2}`
				: y1 === y2
					? `${MONTHS[m1 - 1]}${joiner}${MONTHS[m2 - 1]} ${y2}`
					: `${MONTHS[m1 - 1]} ${y1}${joiner}${MONTHS[m2 - 1]} ${y2}`;
	const place = placeName(photos);
	return place ? `${place} · ${when}` : when;
}

export function suggestionRoutes(h: Helpers): Route[] {
	function answersOf(user: MockUser): Set<string> {
		const answers = h.state().suggestionAnswers;
		if (!answers.has(user.id)) answers.set(user.id, new Set());
		return answers.get(user.id)!;
	}

	function open(user: MockUser): { key: string; title: string; photos: MockAsset[] }[] {
		if (user.role === 'guest') return [];
		const byTime = h
			.filtered(user, { guessed_date: false })
			.sort((a, b) => time(a) - time(b) || a.id - b.id);
		const peopleOf = new Map<number, Set<number>>();
		for (const f of h.state().faces)
			if (f.person_id !== null)
				peopleOf.set(f.asset_id, (peopleOf.get(f.asset_id) ?? new Set()).add(f.person_id));
		const answered = answersOf(user);
		const inAlbums = new Set(
			h
				.state()
				.albums.filter(
					(al) => al.owner_id === user.id || al.members.some((m) => m.user_id === user.id)
				)
				.flatMap((al) => al.items)
		);
		return events(byTime, (a) => peopleOf.get(a.id) ?? new Set())
			.reverse()
			.map((photos) => ({ key: String(Math.min(...photos.map((a) => a.id))), photos }))
			.filter(
				({ key, photos }) =>
					!answered.has(key) &&
					photos.filter((a) => inAlbums.has(a.id)).length < MOSTLY_IN_ALBUMS * photos.length
			)
			.map(({ key, photos }) => ({ key, title: title(photos), photos }));
	}

	function find(user: MockUser, key: string) {
		const found = open(user).find((s) => s.key === key);
		if (!found) throw new HttpError(404, GONE);
		return found;
	}

	function member(user: MockUser) {
		if (user.role === 'guest') throw new HttpError(403, 'Guests cannot create albums.');
	}

	return [
		[
			'GET',
			/^\/api\/album-suggestions$/,
			(ctx) => {
				const user = me(ctx);
				const out: AlbumSuggestion[] = open(user)
					.slice(0, MAX_SUGGESTIONS)
					.map(({ key, title, photos }) => ({
						key,
						title,
						from: photos[0].taken_at.slice(0, 10),
						to: photos.at(-1)!.taken_at.slice(0, 10),
						count: photos.length,
						cover: h.toOut(user, photos[Math.floor(photos.length / 2)]),
						items: photos.slice(0, PREVIEW).map((a) => h.toOut(user, a))
					}));
				return ok(out);
			}
		],
		[
			'POST',
			/^\/api\/album-suggestions\/([^/]+)\/keep$/,
			(ctx) => {
				const user = me(ctx);
				member(user);
				const key = decodeURIComponent(ctx.params[0]);
				const found = find(user, key);
				answersOf(user).add(key);
				const album: MockAlbum = {
					id: h.state().nextId.album++,
					title: found.title,
					description: null,
					owner_id: user.id,
					items: found.photos.map((a) => a.id),
					cover_asset_id: null,
					members: [],
					updated_at: nowIso()
				};
				h.state().albums.push(album);
				return ok(h.albumSummary(user, album), 201);
			}
		],
		[
			'POST',
			/^\/api\/album-suggestions\/([^/]+)\/discard$/,
			(ctx) => {
				const user = me(ctx);
				member(user);
				const key = decodeURIComponent(ctx.params[0]);
				find(user, key);
				answersOf(user).add(key);
				return noContent;
			}
		]
	];
}
