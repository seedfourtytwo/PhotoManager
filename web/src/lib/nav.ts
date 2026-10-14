/** Where things are: the places of the app and what sits behind the account button. */
import type { BackupHealth } from './api';
import { photos } from './format';
import type { IconName } from './icons';
import type { CollectionsRow } from './look';
import type { MenuItem } from './menu';

export type Place = {
	href: string;
	label: string;
	icon: IconName;
	match: (path: string) => boolean;
};

/** True for the route itself and anything below it, never for a longer look-alike name. */
const under = (path: string, route: string) => path === route || path.startsWith(`${route}/`);

/** Calendar is a view of Library; people, places and albums are reached through Collections. */
export const PLACES: Place[] = [
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

const COLLECTIONS: Record<CollectionsRow, { href: string; label: string }> = {
	people: { href: '/people', label: 'People' },
	places: { href: '/map', label: 'Places' },
	albums: { href: '/albums', label: 'Albums' }
};

/** The rows of the Collections page: the ones the account's look names, in its order. */
export function collectionRows(shown: readonly CollectionsRow[]) {
	return shown.map((row) => ({ row, ...COLLECTIONS[row] }));
}

export function accountItems(
	who: { isAdmin: boolean; waiting: number },
	path: string,
	signOut: () => void
): MenuItem[] {
	const link = (label: string, href: string, count?: number, countLabel?: string): MenuItem => ({
		label,
		href,
		count,
		countLabel,
		current: under(path, href)
	});
	return [
		link('To review', '/review', who.waiting, photos(who.waiting)),
		link('Trash', '/trash'),
		link('Settings', '/settings'),
		...(who.isAdmin ? [link('Admin', '/admin')] : []),
		{ label: 'Sign out', run: signOut }
	];
}

/** The first letter of a name for the account button; a whole emoji counts as one character. */
export function initialOf(name: string | undefined): string {
	return ([...(name ?? '').trim()][0] ?? '?').toUpperCase();
}

/**
 * The one sentence an admin's avatar dot stands for (the first backup problem), or null: a
 * member never sees backup state, and all being well shows nothing.
 */
export function attentionOf(isAdmin: boolean, health: BackupHealth | null): string | null {
	if (!isAdmin || !health) return null;
	return health.problems[0]?.message ?? null;
}
