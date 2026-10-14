/**
 * Home (issue 54): on this day, memories (trips away from home, months at home) and what is
 * new, as the server works them out (backend domain/memories.py, domain/on_this_day.py,
 * app/home.py). "Today" is the mock clock's UTC date.
 */
import type { HomeData, HomeFilter, Memory, OnThisDay } from '../../src/lib/api/types.ts';
import { setFor } from '../access.ts';
import { me, ok, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';
import type { MockAsset, MockUser } from '../types.ts';

const DAY = 86_400_000;
const MAX_GAP = 2 * DAY;
const MAX_TRIP = 21 * DAY;
const MIN_PHOTOS = 10;
const MIN_AT_HOME = 20;
const MAX_MEMORIES = 8;
const NEWEST_FIRST = 2;
const AROUND = 3;
const NEW_DAYS = 7;
const NEW_SHOWN = 12;
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

const time = (a: MockAsset) => Date.parse(`${a.taken_at}Z`);
const dayOf = (a: MockAsset) => a.taken_at.slice(0, 10);
const isoDay = (ms: number) => new Date(ms).toISOString().slice(0, 10);
const placeOf = (a: MockAsset) =>
	a.place ? a.place.place.city || a.place.place.region || a.place.place.country : null;
const filterOf = (from: string, to: string): HomeFilter => ({ from, to, guessed_date: false });

/** The place most photos with one were taken at; a tie goes to the first seen. */
function dominantPlace(photos: MockAsset[]): string | null {
	const counts = new Map<string, number>();
	for (const a of photos) {
		const place = placeOf(a);
		if (place) counts.set(place, (counts.get(place) ?? 0) + 1);
	}
	let best: string | null = null;
	for (const [place, n] of counts) if (best === null || n > counts.get(best)!) best = place;
	return best;
}

/** "July 2024", "July and August 2024", "December 2023 to February 2024". */
function periodWords(first: string, last: string): string {
	const [y1, m1] = first.split('-').map(Number);
	const [y2, m2] = last.split('-').map(Number);
	const months = (y2 - y1) * 12 + m2 - m1;
	const joiner = months === 1 ? ' and ' : ' to ';
	if (months === 0) return `${MONTHS[m2 - 1]} ${y2}`;
	if (y1 === y2) return `${MONTHS[m1 - 1]}${joiner}${MONTHS[m2 - 1]} ${y2}`;
	return `${MONTHS[m1 - 1]} ${y1}${joiner}${MONTHS[m2 - 1]} ${y2}`;
}

/**
 * Where each photo (in time order) was taken when away from home (the city with the most
 * photos); null at home. A photo without a place goes with the nearest photo that has one,
 * within two days; when two places are as near, or none is, it counts as home.
 */
function awayPlaces(byTime: MockAsset[]): (string | null)[] {
	const home = dominantPlace(byTime);
	const own = byTime.map(placeOf);
	const nearest = (i: number): string | null => {
		let best: { gap: number; places: Set<string> } | null = null;
		for (const step of [-1, 1]) {
			let j = i + step;
			while (j >= 0 && j < byTime.length && !own[j]) j += step;
			if (j < 0 || j >= byTime.length) continue;
			const gap = Math.abs(time(byTime[j]) - time(byTime[i]));
			if (gap > MAX_GAP) continue;
			if (!best || gap < best.gap) best = { gap, places: new Set([own[j]!]) };
			else if (gap === best.gap) best.places.add(own[j]!);
		}
		return best && best.places.size === 1 ? [...best.places][0] : null;
	};
	return byTime.map((_, i) => {
		const place = own[i] ?? nearest(i);
		return place === home ? null : place;
	});
}

/** Runs away from home in one city, at most two days apart and 21 days long, ten at least. */
function trips(byTime: MockAsset[], places: (string | null)[]): [string, MockAsset[]][] {
	const found: [string, MockAsset[]][] = [];
	let run: MockAsset[] = [];
	let runPlace = '';
	byTime.forEach((a, i) => {
		const place = places[i];
		const gap = run.length ? time(a) - time(run.at(-1)!) : 0;
		const length = run.length ? time(a) - time(run[0]) : 0;
		if (run.length && (place !== runPlace || gap > MAX_GAP || length > MAX_TRIP)) {
			found.push([runPlace, run]);
			run = [];
		}
		if (place !== null) {
			runPlace = place;
			run.push(a);
		}
	});
	found.push([runPlace, run]);
	return found.filter(([, t]) => t.length >= MIN_PHOTOS);
}

/** `size` of `items`, a different page each day; when all fit, their order turns instead. */
function turn<T>(items: T[], today: number, size: number): T[] {
	const n = items.length;
	if (n === 0) return [];
	const step = n > size ? size : 1;
	const ordinal = Math.floor(today / DAY);
	const start = (ordinal * step) % n;
	return Array.from({ length: Math.min(size, n) }, (_, i) => items[(start + i) % n]);
}

/** Today's month and day in `year`; 29 February is 28 February in a common year. */
function anniversary(today: string, year: number): string {
	const monthDay = today.slice(5);
	const leap = new Date(Date.UTC(year, 1, 29)).getUTCMonth() === 1;
	return `${year}-${monthDay === '02-29' && !leap ? '02-28' : monthDay}`;
}

export function homeRoutes(h: Helpers): Route[] {
	const cover = (user: MockUser, photos: MockAsset[]) =>
		photos.find((a) => setFor(h.state().favourites, user.id).has(a.id)) ?? photos[0];

	function memories(user: MockUser, byTime: MockAsset[], today: number): Memory[] {
		const places = awayPlaces(byTime);
		const all = [
			...trips(byTime, places).map(([place, trip]): Memory => {
				const [from, to] = [dayOf(trip[0]), dayOf(trip.at(-1)!)];
				const period = periodWords(from, to);
				return {
					key: `${from}_${to}`,
					title: place ? `${place}, ${period}` : period,
					from,
					to,
					count: trip.length,
					cover: h.toOut(user, cover(user, trip)),
					filter: filterOf(from, to)
				};
			}),
			...monthsAtHome(user, byTime, places)
		].sort((a, b) => b.to.localeCompare(a.to) || b.from.localeCompare(a.from));
		const rest = all.slice(NEWEST_FIRST);
		return [...all.slice(0, NEWEST_FIRST), ...turn(rest, today, MAX_MEMORIES - NEWEST_FIRST)];
	}

	/** Each calendar month with twenty photos at home: all of that month, a cover from home. */
	function monthsAtHome(user: MockUser, byTime: MockAsset[], places: (string | null)[]): Memory[] {
		const months = new Map<string, { all: number; home: MockAsset[] }>();
		byTime.forEach((a, i) => {
			const month = a.taken_at.slice(0, 7);
			const entry = months.get(month) ?? { all: 0, home: [] };
			entry.all++;
			if (places[i] === null) entry.home.push(a);
			months.set(month, entry);
		});
		return [...months]
			.filter(([, m]) => m.home.length >= MIN_AT_HOME)
			.map(([month, m]) => {
				const [y, mo] = month.split('-').map(Number);
				const from = `${month}-01`;
				const to = isoDay(Date.UTC(y, mo, 0));
				return {
					key: `${from}_${to}`,
					title: periodWords(from, from),
					from,
					to,
					count: m.all,
					cover: h.toOut(user, cover(user, m.home)),
					filter: filterOf(from, to)
				};
			});
	}

	function onThisDay(user: MockUser, byTime: MockAsset[], today: number): OnThisDay | null {
		const day = isoDay(today);
		const thisYear = Number(day.slice(0, 4));
		const years = [...new Set(byTime.map((a) => Number(a.taken_at.slice(0, 4))))]
			.flatMap((y) => [y, y + 1])
			.filter((y, i, all) => y < thisYear && all.indexOf(y) === i)
			.sort((a, b) => b - a);
		for (const exact of [true, false]) {
			let picked: { year: number; from: string; to: string; photos: MockAsset[] } | null = null;
			for (const year of years) {
				const at = Date.parse(`${anniversary(day, year)}T00:00:00Z`);
				const [from, to] = exact ? [at, at] : [at - AROUND * DAY, at + AROUND * DAY];
				const [first, last] = [isoDay(from), isoDay(to)];
				const photos = byTime.filter((a) => dayOf(a) >= first && dayOf(a) <= last);
				if (photos.length && (!picked || photos.length > picked.photos.length))
					picked = { year, from: first, to: last, photos };
			}
			if (picked) return dayOut(user, picked, exact, thisYear, day);
		}
		return null;
	}

	function dayOut(
		user: MockUser,
		picked: { year: number; from: string; to: string; photos: MockAsset[] },
		exact: boolean,
		thisYear: number,
		today: string
	): OnThisDay {
		const ids = new Set(picked.photos.map((a) => a.id));
		const onThem = new Map<number, number>();
		for (const f of h.state().faces)
			if (f.person_id !== null && ids.has(f.asset_id))
				onThem.set(f.person_id, (onThem.get(f.person_id) ?? 0) + 1);
		const people = h
			.state()
			.people.filter((p) => p.name && !p.hidden && onThem.has(p.id))
			.sort((a, b) => onThem.get(b.id)! - onThem.get(a.id)! || a.id - b.id)
			.map((p) => ({ id: p.id, name: p.name! }));
		return {
			day: anniversary(today, picked.year),
			years_ago: thisYear - picked.year,
			exact,
			count: picked.photos.length,
			cover: h.toOut(user, cover(user, picked.photos)),
			place: dominantPlace(picked.photos),
			people,
			filter: filterOf(picked.from, picked.to)
		};
	}

	function arrivals(user: MockUser, today: number): HomeData['new'] {
		const since = today - NEW_DAYS * DAY;
		const fresh = h
			.filtered(user, {})
			.filter((a) => Date.parse(`${a.imported_at}Z`) >= since)
			.sort((a, b) => b.imported_at.localeCompare(a.imported_at) || b.id - a.id);
		const counts = new Map<number, number>();
		for (const a of fresh) {
			const from = a.sources[0].source_id;
			if (h.sourceLevel(user, from) !== null) counts.set(from, (counts.get(from) ?? 0) + 1);
		}
		const label = (id: number) => h.state().sources.find((s) => s.id === id)?.label ?? '';
		return {
			count: fresh.length,
			days: NEW_DAYS,
			sources: [...counts]
				.map(([id, count]) => ({ id, label: label(id), count }))
				.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label) || a.id - b.id),
			items: fresh.slice(0, NEW_SHOWN).map((a) => h.toOut(user, a))
		};
	}

	return [
		[
			'GET',
			/^\/api\/home$/,
			(ctx) => {
				const user = me(ctx);
				const today = h.now();
				const byTime = h
					.filtered(user, { guessed_date: false })
					.sort((a, b) => time(a) - time(b) || a.id - b.id);
				const home: HomeData = {
					on_this_day: onThisDay(user, byTime, today),
					memories: memories(user, byTime, today),
					new: arrivals(user, today)
				};
				return ok(home);
			}
		]
	];
}
