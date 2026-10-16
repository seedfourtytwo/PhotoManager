/** The sections of Settings (You and Admin as one place, spec flight/admin-settings-auth §1). */
import type { IconName } from './icons';

export type SectionId =
	'you' | 'appearance' | 'phones' | 'overview' | 'folders' | 'backups' | 'people' | 'search';

export type Section = {
	id: SectionId;
	href: string;
	label: string;
	icon: IconName;
	/** Who sees it: everyone, whoever can add photos (Phones), or admins. */
	for: 'all' | 'edit' | 'admin';
};

/** In the order of the sidebar: the person's own sections, then the admin ones. */
export const SECTIONS: readonly Section[] = [
	{ id: 'you', href: '/settings', label: 'You', icon: 'person', for: 'all' },
	{ id: 'appearance', href: '/settings/appearance', label: 'Appearance', icon: 'sun', for: 'all' },
	{ id: 'phones', href: '/settings/phones', label: 'Phones', icon: 'phone', for: 'edit' },
	{ id: 'overview', href: '/settings/overview', label: 'Overview', icon: 'shield', for: 'admin' },
	{ id: 'folders', href: '/settings/folders', label: 'Folders', icon: 'folder', for: 'admin' },
	{ id: 'backups', href: '/settings/backups', label: 'Backups', icon: 'cloud', for: 'admin' },
	{ id: 'people', href: '/settings/people', label: 'People', icon: 'person', for: 'admin' },
	{ id: 'search', href: '/settings/search', label: 'Search & faces', icon: 'sparkle', for: 'admin' }
];

/** The sections a person sees: admin ones only for an admin, Phones only for who can add photos. */
export function sectionsFor(who: { isAdmin: boolean; canEdit: boolean }): Section[] {
	return SECTIONS.filter((s) => s.for === 'all' || (s.for === 'edit' ? who.canEdit : who.isAdmin));
}

/** The section a path shows, or undefined outside Settings. */
export function sectionOf(path: string): Section | undefined {
	const trimmed = path.length > 1 ? path.replace(/\/$/, '') : path;
	return SECTIONS.find((s) => s.href === trimmed);
}

/**
 * The sign-in name made from a display name (setup): lower case, accents dropped, words joined
 * by dots, only what the server takes (letters, digits, . _ -, 64 at most). '' when nothing is left.
 */
export function signInName(name: string): string {
	return name
		.normalize('NFD')
		.replace(/\p{M}/gu, '')
		.toLowerCase()
		.split(/\s+/)
		.map((word) => word.replace(/[^a-z0-9_-]/g, ''))
		.filter(Boolean)
		.join('.')
		.slice(0, 64);
}

/** Where an old Admin address (/admin, /admin#a-backups) leads now. */
export function adminTarget(hash: string): string {
	return hash === '#a-backups' ? '/settings/backups' : '/settings/overview';
}
