/** Where things are: the places of the app, how a page change moves, and who you are. */
import type { BackupHealth } from './api';
import { problemWords } from './backups';
import type { IconName } from './icons';
import type { CollectionsRow } from './look';
import type { PageMove } from './motion';

export type Place = {
	href: string;
	label: string;
	icon: IconName;
	match: (path: string) => boolean;
};

/** True for the route itself and anything below it, never for a longer look-alike name. */
const under = (path: string, route: string) => path === route || path.startsWith(`${route}/`);

/**
 * Home tells the family's story (spec 2026-10-14 §9); Calendar is a view of Library; people,
 * places and albums are reached through Collections.
 */
export const PLACES: Place[] = [
	{ href: '/home', label: 'Home', icon: 'home', match: (path) => path === '/home' },
	{
		href: '/',
		label: 'Library',
		icon: 'library',
		match: (path) => path === '/' || path === '/calendar'
	},
	{
		href: '/collections',
		label: 'Collections',
		icon: 'collections',
		match: (path) =>
			['/collections', '/people', '/map', '/albums'].some((route) => under(path, route))
	}
];

/** The places of the dock: Home only when the account's look shows it (`showToday`). */
export function placesFor(showHome: boolean): Place[] {
	return showHome ? PLACES : PLACES.filter((place) => place.href !== '/home');
}

const COLLECTIONS: Record<CollectionsRow, { href: string; label: string }> = {
	people: { href: '/people', label: 'People' },
	places: { href: '/map', label: 'Places' },
	albums: { href: '/albums', label: 'Albums' }
};

/** The rows of the Collections page: the ones the account's look names, in its order. */
export function collectionRows(shown: readonly CollectionsRow[]) {
	return shown.map((row) => ({ row, ...COLLECTIONS[row] }));
}

/** The first letter of a name for the avatar; a whole emoji counts as one character. */
export function initialOf(name: string | undefined): string {
	return ([...(name ?? '').trim()][0] ?? '?').toUpperCase();
}

/**
 * What an admin's avatar dot stands for (the first backup problem's plain headline), or null:
 * a member never sees backup state, and all being well shows nothing.
 */
export function attentionOf(isAdmin: boolean, health: BackupHealth | null): string | null {
	if (!isAdmin || !health?.problems.length) return null;
	return problemWords(health.problems[0]).headline;
}

/** The pages the bar leads to: going from one to another is switching places. */
const TOPS = new Set([...PLACES.map((place) => place.href), '/calendar', '/search']);

/** The word on a Back that leads to `path`: the bar's name for its own pages, else Back. */
export function backLabel(path: string): string {
	if (path === '/search') return 'Search';
	if (!TOPS.has(path)) return 'Back';
	return PLACES.find((place) => place.match(path))?.label ?? 'Back';
}

/** How far in a page sits: the bar's pages 0, a page opened from one 1, and so on. */
function depthOf(path: string): number {
	if (TOPS.has(path)) return 0;
	return path.split('/').filter(Boolean).length;
}

const MOVES: readonly string[] = ['forward', 'back', 'switch'] satisfies PageMove[];

/**
 * How a page change looks (spec §2, Motion): a page opened from this one slides in from the
 * right, Back slides from the left, another place of the bar cross-fades. `asked` is what the
 * pressed link says (`data-move`), `delta` the history's step, `shown` that the browser has
 * already drawn the way back itself (a swipe), so drawing it again would show it twice.
 * Nothing moves when only the query or the photo changes.
 */
export function pageMove(step: {
	from: string;
	to: string;
	delta?: number;
	asked?: string | null;
	shown?: boolean;
}): PageMove | null {
	const { from, to, delta, asked } = step;
	if (from === to || step.shown) return null;
	if (asked && MOVES.includes(asked)) return asked as PageMove;
	if (TOPS.has(from) && TOPS.has(to)) return 'switch';
	if (delta) return delta < 0 ? 'back' : 'forward';
	return depthOf(to) < depthOf(from) ? 'back' : 'forward';
}
