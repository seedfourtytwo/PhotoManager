/** Where things are: the places of the app and what sits behind the account button. */
import type { MenuItem } from './components/Menu.svelte';
import type { IconName } from './icons';
import type { CollectionsRow } from './look';

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

const COLLECTIONS: Record<CollectionsRow, { href: string; label: string; about: string }> = {
	people: {
		href: '/people',
		label: 'People',
		about: 'Everyone the app has recognised in your photos.'
	},
	places: { href: '/map', label: 'Places', about: 'Your photos on a map.' },
	albums: { href: '/albums', label: 'Albums', about: 'Sets of photos you put together.' }
};

/** The rows of the Collections page: the ones the account's look names, in its order. */
export function collectionRows(shown: readonly CollectionsRow[]) {
	return shown.map((row) => COLLECTIONS[row]);
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
		link(
			'To review',
			'/review',
			who.waiting,
			`${who.waiting} ${who.waiting === 1 ? 'photo' : 'photos'}`
		),
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
