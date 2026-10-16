import { page } from 'vitest/browser';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { notice, viewport } from '$lib/app.svelte';
import CollectionRows from './CollectionRows.svelte';

const PEOPLE = [
	{ id: 1, name: null, face_count: 40, asset_count: 30, cover: null, portrait: null },
	{ id: 2, name: 'Sam', face_count: 31, asset_count: 27, cover: null, portrait: null }
];
const album = (id: number, title: string, updated_at = '2026-03-01T10:00:00') => ({
	id,
	title,
	description: null,
	cover: null,
	count: 12,
	owner_id: 1,
	role: 'owner',
	updated_at
});
const ALBUMS = [album(7, 'Brittany')];
const place = (name: string, kind: 'country' | 'city', country: string, count: number) => ({
	name,
	kind,
	country,
	count,
	cover: { asset_id: count, url: `/api/assets/${count}/thumb`, width: 4, height: 3 },
	lat: 47,
	lon: -3
});
const PLACES = [place('Carnac', 'city', 'France', 36), place('France', 'country', 'France', 180)];

type Answers = Partial<Record<'people' | 'albums' | 'places', unknown>>;

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
			{ '/api/people': 'people', '/api/albums': 'albums', '/api/places': 'places' } as const
		)[url.pathname];
		if (key) return key in answers ? json(answers[key]) : json({ detail: 'broken' }, 500);
		return json({ detail: 'not here' }, 404);
	});
	return asked;
}

const LAPTOP = 1440;
beforeEach(async () => {
	await page.viewport(LAPTOP, 900);
	viewport.width = LAPTOP;
});
afterEach(() => {
	vi.unstubAllGlobals();
	notice.text = '';
});

const row = (name: string) =>
	page.getByRole('listitem').filter({ hasText: new RegExp(`^${name}`) });

describe('Collections rows', () => {
	it('show who, what and where is behind each row, in the order given', async () => {
		stubApi({ people: PEOPLE, albums: ALBUMS, places: PLACES });
		render(CollectionRows, { rows: ['albums', 'people', 'places'] });

		// a face says who, not how many
		await expect
			.element(page.getByRole('link', { name: 'Sam', exact: true }))
			.toHaveAttribute('href', '/people/2');
		await expect
			.element(page.getByRole('link', { name: 'Someone', exact: true }))
			.toHaveAttribute('href', '/people/1');
		expect(row('People').element().textContent).not.toMatch(/\d/);
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
			[...row(name).element().querySelectorAll('a .name, a .title')].map((el) => el.textContent);
		expect(names('People')).toEqual(['Sam', 'Someone']);
		expect(names('Places')).toEqual(['France', 'Carnac']);
	});

	it('each row still leads to its own page', async () => {
		stubApi({ people: PEOPLE, albums: ALBUMS, places: PLACES });
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

	it('the places come in one request, each with its newest photo as the cover', async () => {
		const asked = stubApi({ places: PLACES });
		render(CollectionRows, { rows: ['places'] });
		const france = page.getByRole('link', { name: 'France 180 photos' });
		await expect.element(france).toBeInTheDocument();
		await expect
			.poll(() => france.element().querySelector('img')?.getAttribute('src'))
			.toBe('/api/assets/180/thumb');
		expect(asked).toEqual(['/api/places']);
	});

	it('a country that is one city and nothing else is not shown twice', async () => {
		stubApi({
			places: [
				place('France', 'country', 'France', 180),
				place('Portugal', 'country', 'Portugal', 73),
				place('Lisbon', 'city', 'Portugal', 73)
			]
		});
		render(CollectionRows, { rows: ['places'] });
		await expect.element(page.getByRole('link', { name: 'Lisbon 73 photos' })).toBeVisible();
		await expect.element(page.getByRole('link', { name: 'France 180 photos' })).toBeVisible();
		expect(page.getByRole('link', { name: /^Portugal/ }).elements()).toHaveLength(0);
	});

	it('a laptop row is whole: its cards fill the width and no orphan starts a second row', async () => {
		const many = Array.from({ length: 7 }, (_, i) =>
			album(i + 1, `Album ${i + 1}`, `2026-03-0${i + 1}T10:00:00`)
		);
		stubApi({ albums: many });
		render(CollectionRows, { rows: ['albums'] });
		await expect.element(page.getByRole('link', { name: /^Album 7/ })).toBeVisible();
		const cards = row('Albums').element().querySelectorAll('a.card');
		const boxes = [...cards].map((card) => card.getBoundingClientRect());
		expect(new Set(boxes.map((b) => Math.round(b.top))).size).toBe(1); // one row
		const strip = cards[0].closest('.grid')!.getBoundingClientRect();
		expect(Math.round(boxes.at(-1)!.right)).toBe(Math.round(strip.right)); // to its end
	});

	it('a phone row is a rail whose next card peeks in at the screen edge', async () => {
		await page.viewport(390, 844);
		viewport.width = 390;
		stubApi({ places: [1, 2, 3, 4].map((n) => place(`Town ${n}`, 'city', 'France', 10 * n)) });
		render(CollectionRows, { rows: ['places'] });
		await expect.element(page.getByRole('link', { name: /^Town 4/ })).toBeVisible();
		const cards = [...row('Places').element().querySelectorAll('a.card')];
		const edge = window.innerWidth;
		const cut = cards.find((card) => {
			const box = card.getBoundingClientRect();
			return box.left < edge && box.right > edge;
		});
		expect(cut).toBeDefined(); // a card runs off the edge, so the row reads as "more"
	});

	it('do not ask for a row the look leaves out', async () => {
		const asked = stubApi({ people: PEOPLE, albums: ALBUMS, places: PLACES });
		render(CollectionRows, { rows: ['albums'] });
		await expect.element(page.getByRole('link', { name: 'Brittany 12 photos' })).toBeVisible();
		expect(asked).toEqual(['/api/albums']);
		expect(page.getByRole('heading', { level: 2 }).elements()).toHaveLength(1);
	});

	it('an empty row says what will be there', async () => {
		stubApi({ people: [], albums: [], places: [] });
		render(CollectionRows, { rows: ['people', 'places', 'albums'] });
		await expect.element(page.getByText('No people yet.')).toBeVisible();
		await expect.element(page.getByText('No places yet.')).toBeVisible();
		await expect.element(page.getByText('No albums yet.')).toBeVisible();
	});

	it('a row that cannot load says so and leaves the others standing', async () => {
		stubApi({ albums: ALBUMS, places: PLACES });
		render(CollectionRows, { rows: ['people', 'places', 'albums'] });
		await expect.element(page.getByRole('link', { name: 'Brittany 12 photos' })).toBeVisible();
		await expect.element(page.getByRole('link', { name: 'France 180 photos' })).toBeVisible();
		await expect.poll(() => notice.text).not.toBe('');
		await expect.element(page.getByRole('link', { name: 'People', exact: true })).toBeVisible();
	});
});
