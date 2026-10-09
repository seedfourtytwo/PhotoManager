import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { notice } from '$lib/app.svelte';
import { makeAsset } from '$lib/testing/fixtures';
import CollectionRows from './CollectionRows.svelte';

const PEOPLE = [
	{ id: 1, name: null, face_count: 40, asset_count: 30, cover: null },
	{ id: 2, name: 'Sam', face_count: 31, asset_count: 27, cover: null }
];
const ALBUMS = [
	{
		id: 7,
		title: 'Brittany',
		description: null,
		cover: null,
		count: 12,
		owner_id: 1,
		role: 'owner',
		updated_at: '2026-03-01T10:00:00'
	}
];
const FACETS = {
	years: [],
	sources: [],
	cameras: [],
	places: [
		{ name: 'Carnac', count: 36 },
		{ name: 'France', count: 180 }
	],
	guessed_dates: 0,
	total: 180
};

type Answers = Partial<Record<'people' | 'albums' | 'facets', unknown>>;

/** Answers the page's requests; a missing answer is a server error. Returns the paths asked for. */
function stubApi(answers: Answers) {
	const asked: string[] = [];
	vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
		const url = new URL(String(input), 'http://app');
		asked.push(url.pathname + url.search);
		const json = (body: unknown, status = 200) =>
			new Response(JSON.stringify(body), {
				status,
				headers: { 'content-type': 'application/json' }
			});
		const key = (
			{ '/api/people': 'people', '/api/albums': 'albums', '/api/assets/facets': 'facets' } as const
		)[url.pathname];
		if (key) return key in answers ? json(answers[key]) : json({ detail: 'broken' }, 500);
		if (url.pathname === '/api/assets')
			return json({ items: [makeAsset(url.searchParams.get('place') === 'France' ? 5 : 6)] });
		return json({ detail: 'not here' }, 404);
	});
	return asked;
}

afterEach(() => {
	vi.unstubAllGlobals();
	notice.text = '';
});

const row = (name: string) =>
	page.getByRole('listitem').filter({ hasText: new RegExp(`^${name}`) });

describe('Collections rows', () => {
	it('show who, what and where is behind each row, in the order given', async () => {
		stubApi({ people: PEOPLE, albums: ALBUMS, facets: FACETS });
		render(CollectionRows, { rows: ['albums', 'people', 'places'] });

		await expect
			.element(page.getByRole('link', { name: 'Sam 27 photos' }))
			.toHaveAttribute('href', '/people/2');
		await expect
			.element(page.getByRole('link', { name: 'Someone 30 photos' }))
			.toHaveAttribute('href', '/people/1');
		await expect
			.element(page.getByRole('link', { name: 'Brittany 12 photos' }))
			.toHaveAttribute('href', '/albums/7');
		await expect
			.element(page.getByRole('link', { name: 'France 180 photos' }))
			.toHaveAttribute('href', '/?place=France');

		const headings = page.getByRole('heading', { level: 2 }).elements();
		expect(headings.map((h) => h.textContent?.trim())).toEqual(['Albums', 'People', 'Places']);
		// named people before the unnamed, the place with the most photos first
		const names = (name: string) =>
			[...row(name).element().querySelectorAll('.rail a .name')].map((el) => el.textContent);
		expect(names('People')).toEqual(['Sam', 'Someone']);
		expect(names('Places')).toEqual(['France', 'Carnac']);
	});

	it('each row still leads to its own page', async () => {
		stubApi({ people: PEOPLE, albums: ALBUMS, facets: FACETS });
		render(CollectionRows, { rows: ['people', 'places', 'albums'] });
		for (const [name, href] of [
			['People', '/people'],
			['Places', '/map'],
			['Albums', '/albums']
		])
			await expect
				.element(page.getByRole('link', { name, exact: true }))
				.toHaveAttribute('href', href);
	});

	it('a place shows one of its photos', async () => {
		stubApi({ facets: FACETS });
		render(CollectionRows, { rows: ['places'] });
		const france = page.getByRole('link', { name: 'France 180 photos' });
		await expect.element(france).toBeInTheDocument();
		await expect
			.poll(() => france.element().querySelector('img')?.getAttribute('src'))
			.toBe('/api/assets/5/thumb');
	});

	it('do not ask for a row the look leaves out', async () => {
		const asked = stubApi({ people: PEOPLE, albums: ALBUMS, facets: FACETS });
		render(CollectionRows, { rows: ['albums'] });
		await expect.element(page.getByRole('link', { name: 'Brittany 12 photos' })).toBeVisible();
		expect(asked).toEqual(['/api/albums']);
		expect(page.getByRole('heading', { level: 2 }).elements()).toHaveLength(1);
	});

	it('an empty row says what will be there', async () => {
		stubApi({ people: [], albums: [], facets: { ...FACETS, places: [] } });
		render(CollectionRows, { rows: ['people', 'places', 'albums'] });
		await expect.element(page.getByText('No people yet.')).toBeVisible();
		await expect.element(page.getByText('No places yet.')).toBeVisible();
		await expect.element(page.getByText('No albums yet.')).toBeVisible();
	});

	it('a row that cannot load says so and leaves the others standing', async () => {
		stubApi({ albums: ALBUMS, facets: FACETS });
		render(CollectionRows, { rows: ['people', 'places', 'albums'] });
		await expect.element(page.getByRole('link', { name: 'Brittany 12 photos' })).toBeVisible();
		await expect.element(page.getByRole('link', { name: 'France 180 photos' })).toBeVisible();
		await expect.poll(() => notice.text).not.toBe('');
		await expect.element(page.getByRole('link', { name: 'People', exact: true })).toBeVisible();
	});
});
