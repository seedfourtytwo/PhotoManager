import { describe, expect, it } from 'vitest';
import { SECTIONS, adminTarget, sectionOf, sectionsFor, signInName } from './settings';

const ids = (list: { id: string }[]) => list.map((s) => s.id);

describe('Settings sections by role', () => {
	it('an admin sees their own sections, then the admin ones', () => {
		expect(ids(sectionsFor({ isAdmin: true, canEdit: true }))).toEqual([
			'you',
			'appearance',
			'phones',
			'overview',
			'folders',
			'backups',
			'people',
			'search'
		]);
	});
	it('a member sees no admin section', () => {
		expect(ids(sectionsFor({ isAdmin: false, canEdit: true }))).toEqual([
			'you',
			'appearance',
			'phones'
		]);
	});
	it('a guest, who cannot add photos, has no Phones either', () => {
		expect(ids(sectionsFor({ isAdmin: false, canEdit: false }))).toEqual(['you', 'appearance']);
	});
	it('every section has its own address under /settings', () => {
		const hrefs = SECTIONS.map((s) => s.href);
		expect(new Set(hrefs).size).toBe(hrefs.length);
		for (const href of hrefs) expect(href).toMatch(/^\/settings(\/[a-z]+)?$/);
	});
});

describe('sectionOf', () => {
	it('names the section a path shows', () => {
		expect(sectionOf('/settings')?.id).toBe('you');
		expect(sectionOf('/settings/backups')?.id).toBe('backups');
		expect(sectionOf('/settings/backups/')?.id).toBe('backups');
	});
	it('is nothing outside Settings', () => {
		expect(sectionOf('/settingsx')).toBeUndefined();
		expect(sectionOf('/admin')).toBeUndefined();
	});
});

describe('signInName: the name to sign in with, made from the one you give', () => {
	it.each([
		['C', 'c'],
		['Léa Müller', 'lea.muller'],
		['  Anna  Bell ', 'anna.bell'],
		["O'Brien & co", 'obrien.co'],
		['😀', '']
	])('%s → %s', (name, expected) => {
		expect(signInName(name)).toBe(expected);
	});
	it('fits the server’s rule: 64 letters, digits, dots, dashes, underscores at most', () => {
		const long = signInName('a'.repeat(100));
		expect(long).toHaveLength(64);
		expect(long).toMatch(/^[A-Za-z0-9._-]{1,64}$/);
	});
});

describe('old Admin addresses', () => {
	it('/admin opens the overview', () => {
		expect(adminTarget('')).toBe('/settings/overview');
	});
	it('the old link to the backups opens Backups', () => {
		expect(adminTarget('#a-backups')).toBe('/settings/backups');
	});
	it('an anchor it does not know still lands on the overview', () => {
		expect(adminTarget('#nothing')).toBe('/settings/overview');
	});
});
