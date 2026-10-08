/** Where things are: the places of the app and what sits behind the account button. */
import type { MenuItem } from './components/Menu.svelte';
import type { IconName } from './icons';

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

export function accountItems(
	who: { isAdmin: boolean; waiting: number },
	path: string,
	signOut: () => void
): MenuItem[] {
	const link = (label: string, href: string, count?: number): MenuItem => ({
		label,
		href,
		count,
		current: under(path, href)
	});
	return [
		link('To review', '/review', who.waiting),
		link('Trash', '/trash'),
		link('Settings', '/settings'),
		...(who.isAdmin ? [link('Admin', '/admin')] : []),
		{ label: 'Sign out', run: signOut }
	];
}
