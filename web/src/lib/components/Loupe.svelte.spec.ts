import { page, userEvent } from 'vitest/browser';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import type { AssetDetail, AssetOut, Face, Person } from '$lib/api';
import { notice, session } from '$lib/app.svelte';
import { makeAsset } from '$lib/testing/fixtures';
import Loupe from './Loupe.svelte';

const pixel = 'data:image/gif;base64,R0lGODlhAQABAAAAACw=';
const photos = [1, 2, 3].map((id) =>
	makeAsset(id, `2019-07-0${id}T10:00:00`, 400, 300, { thumb: { url: pixel } })
);
const detailOf = (asset: AssetOut, camera = `Camera ${asset.id}`): AssetDetail => ({
	...asset,
	name: `Photo ${asset.id}`,
	byte_size: 1000,
	mime_type: 'image/jpeg',
	camera_make: null,
	camera_model: camera,
	latitude: null,
	longitude: null,
	f_number: null,
	exposure_time: null,
	iso: null,
	focal_length: null,
	imported_at: '2020-01-01T00:00:00',
	origins: [],
	albums: [],
	level: 'edit'
});

const sam: Person = {
	id: 5,
	name: 'Sam',
	face_count: 1,
	hidden: false,
	asset_count: 1,
	cover: null,
	portrait: null
};
const samsFace: Face = {
	id: 1,
	asset_id: 2,
	box: { x: 0, y: 0, w: 0.1, h: 0.1 },
	score: 0.9,
	person_id: 5
};

type Call = { method: string; path: string };
/** Every request the viewer made; `hold(path)` keeps the next answer for it back until released. */
function server() {
	const calls: Call[] = [];
	const held = new Map<string, Promise<unknown>>();
	const answer = (method: string, path: string): unknown => {
		const asset = photos.find((a) => path.startsWith(`/api/assets/${a.id}`));
		if (path === '/api/albums') return method === 'GET' ? [] : { id: 9, title: 'Nine' };
		if (path === '/api/people') return [sam];
		if (path.endsWith('/faces')) return path === '/api/assets/2/faces' ? [samsFace] : [];
		if (asset && path.endsWith('/state')) return { ...asset, favourite: true };
		if (asset) return detailOf(asset);
		return {};
	};
	vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
		const call = { method: init?.method ?? 'GET', path: String(input) };
		calls.push(call);
		const key = `${call.method} ${call.path}`;
		const waiting = held.get(key);
		held.delete(key);
		const body = waiting ? await waiting : answer(call.method, call.path);
		return new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json' } });
	});
	return {
		calls,
		count: (method: string, path: string) =>
			calls.filter((c) => c.method === method && c.path === path).length,
		hold(key: string) {
			let release!: (body: unknown) => void;
			held.set(key, new Promise((resolve) => (release = resolve)));
			return release;
		}
	};
}

function open(items = photos, index = 0) {
	const handlers = { onindex: vi.fn(), onclose: vi.fn(), onchanged: vi.fn() };
	const view = render(Loupe, { items, index, ...handlers });
	const stage = document.querySelector<HTMLElement>('.stage')!;
	/** A pointer event on the photo, `dx` to the right of its middle. */
	const finger = (type: string, dx = 0, extra: PointerEventInit = {}) =>
		stage.dispatchEvent(
			new PointerEvent(type, {
				pointerType: 'touch',
				pointerId: 1,
				bubbles: true,
				clientX: 200 + dx,
				clientY: 200,
				...extra
			})
		);
	return { ...handlers, view, finger };
}

const viewer = () => page.getByRole('dialog', { name: 'Photo viewer' });
/** How large the open photo is drawn: 1 is its fit. */
const zoom = () =>
	Number(document.querySelector<HTMLElement>('.stage')!.style.getPropertyValue('--zoom'));
const idle = () => expect.element(viewer(), { timeout: 4000 }).toHaveClass(/idle/);
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

beforeEach(() => {
	session.user = { id: 1, username: 'c', display_name: 'C', role: 'admin', disabled: false };
});
afterEach(() => {
	vi.unstubAllGlobals();
	session.user = null;
});

describe('Loupe: gestures', () => {
	it('a second finger cancels the gesture until every finger is up', async () => {
		server();
		const { finger, onindex, onclose } = open();
		finger('pointerdown');
		finger('pointerdown', 40, { pointerId: 2 });
		// Both fingers drift the same way, far past every swipe threshold: no nearer, no further.
		finger('pointermove', -150);
		finger('pointermove', -110, { pointerId: 2 });
		// A pinch does not pull the photo along either.
		expect(document.querySelector('.stage')!.classList.contains('held')).toBe(false);
		finger('pointerup', -110, { pointerId: 2 });
		// One finger of the pinch is still down: a third touch is no tap and no swipe.
		finger('pointerdown', -110, { pointerId: 3 });
		finger('pointerup', -110, { pointerId: 3, clientY: 400 });
		finger('pointerup', -150);
		expect(onindex).not.toHaveBeenCalled();
		expect(onclose).not.toHaveBeenCalled();
		await tick();
		expect(zoom()).toBe(1);
		// With every finger up, one finger swipes again.
		finger('pointerdown');
		finger('pointerup', -150);
		expect(onindex.mock.calls).toEqual([[1]]);
	});

	it('only the main button is a press: a right click leaves the chrome alone', async () => {
		server();
		const { finger } = open();
		finger('pointerdown', 0, { pointerType: 'mouse', button: 2 });
		finger('pointerup', 0, { pointerType: 'mouse', button: 2 });
		await wait(400);
		await expect.element(viewer()).not.toHaveClass(/idle/);
	});
});

describe('Loupe: zoom', () => {
	const favourites = (calls: Call[]) =>
		calls.filter((c) => c.method !== 'GET' && c.path.endsWith('/state')).length;
	const doubleTap = (finger: ReturnType<typeof open>['finger'], dx = 0) => {
		for (let i = 0; i < 2; i++) {
			finger('pointerdown', dx);
			finger('pointerup', dx);
		}
	};
	const zoomButton = () => page.getByRole('button', { name: 'Zoom' });

	it('a double tap zooms in and does not favourite; the next one goes back to the fit', async () => {
		const { calls } = server();
		const { finger } = open();
		await expect.element(zoomButton()).toHaveAttribute('aria-pressed', 'false');
		doubleTap(finger);
		await tick();
		expect(zoom()).toBe(2.5);
		await expect.element(zoomButton()).toHaveAttribute('aria-pressed', 'true');
		doubleTap(finger);
		await tick();
		expect(zoom()).toBe(1);
		await expect.element(zoomButton()).toHaveAttribute('aria-pressed', 'false');
		expect(favourites(calls)).toBe(0);
	});

	it('two fingers spreading zoom in, and the photo stays zoomed when they lift', async () => {
		server();
		const { finger, onindex, onclose } = open();
		finger('pointerdown', -30);
		finger('pointerdown', 30, { pointerId: 2 });
		finger('pointermove', -60);
		finger('pointermove', 60, { pointerId: 2 });
		await tick();
		expect(zoom()).toBe(2);
		// While the fingers move it follows at once: no easing behind them.
		expect(document.querySelector('.stage')!.classList.contains('moving')).toBe(true);
		finger('pointerup', -60);
		finger('pointerup', 60, { pointerId: 2 });
		await tick();
		expect(zoom()).toBe(2);
		expect(document.querySelector('.stage')!.classList.contains('moving')).toBe(false);
		expect(onindex).not.toHaveBeenCalled();
		expect(onclose).not.toHaveBeenCalled();
	});

	it('fingers squeezed under the fit spring back to it', async () => {
		server();
		const { finger } = open();
		finger('pointerdown', -80);
		finger('pointerdown', 80, { pointerId: 2 });
		finger('pointermove', -50);
		finger('pointermove', 50, { pointerId: 2 });
		await tick();
		expect(zoom()).toBeLessThan(1);
		finger('pointerup', -50);
		finger('pointerup', 50, { pointerId: 2 });
		await tick();
		expect(zoom()).toBe(1);
	});

	it('one finger moves a zoomed photo: it neither steps nor closes', async () => {
		server();
		const { finger, onindex, onclose } = open();
		doubleTap(finger);
		finger('pointerdown');
		finger('pointermove', -150);
		finger('pointerup', -150);
		finger('pointerdown');
		finger('pointermove', 0, { clientY: 500 });
		finger('pointerup', 0, { clientY: 500 });
		expect(onindex).not.toHaveBeenCalled();
		expect(onclose).not.toHaveBeenCalled();
		await tick();
		expect(zoom()).toBe(2.5);
	});

	it('another photo opens at its fit', async () => {
		server();
		const { finger, view } = open();
		doubleTap(finger);
		await tick();
		expect(zoom()).toBe(2.5);
		await view.rerender({ index: 1 });
		await vi.waitFor(() => expect(zoom()).toBe(1));
	});

	it('Z and the Zoom button do what the double tap does', async () => {
		server();
		open();
		await userEvent.keyboard('z');
		await tick();
		expect(zoom()).toBe(2.5);
		await zoomButton().click();
		await tick();
		expect(zoom()).toBe(1);
	});

	it('zooming in puts the chrome away; back at the fit it returns', async () => {
		server();
		const { finger } = open();
		doubleTap(finger);
		await expect.element(viewer()).toHaveClass(/idle/);
		doubleTap(finger);
		await expect.element(viewer()).not.toHaveClass(/idle/);
	});
});

describe('Loupe: chrome', () => {
	it('idle chrome stays reachable for a screen reader', async () => {
		server();
		open();
		await idle();
		const toolbar = page.getByRole('toolbar', { name: 'Photo actions' });
		await expect.element(toolbar).not.toHaveAttribute('inert');
		await expect.element(page.getByRole('button', { name: 'Close' })).toBeInTheDocument();
	});

	it('the press that brings the chrome back does not press what it uncovers', async () => {
		server();
		const { onclose } = open();
		await idle();
		const close = page.getByRole('button', { name: 'Close' }).element() as HTMLElement;
		close.dispatchEvent(new PointerEvent('pointerdown', { pointerType: 'touch', bubbles: true }));
		await expect.element(viewer()).not.toHaveClass(/idle/);
		close.click();
		expect(onclose).not.toHaveBeenCalled();
		close.dispatchEvent(new PointerEvent('pointerdown', { pointerType: 'touch', bubbles: true }));
		close.click();
		expect(onclose).toHaveBeenCalledOnce();
	});

	it('a touch on idle chrome that ends without a click does not eat the next tap', async () => {
		server();
		const { onclose } = open();
		await idle();
		const close = page.getByRole('button', { name: 'Close' }).element() as HTMLElement;
		const touch = (type: string) =>
			close.dispatchEvent(new PointerEvent(type, { pointerType: 'touch', bubbles: true }));
		touch('pointerdown');
		touch('pointercancel');
		// The chrome is in sight: this tap is a tap on Close.
		touch('pointerdown');
		touch('pointerup');
		close.click();
		expect(onclose).toHaveBeenCalledOnce();
		await expect.element(viewer()).not.toHaveClass(/idle/);
	});

	it('stepping to the first or last photo with its edge button leaves the focus on the viewer', async () => {
		server();
		const { view } = open(photos, 1);
		for (const [name, index] of [
			['Previous photo', 0],
			['Next photo', 2]
		] as const) {
			await view.rerender({ index: 1 });
			const edge = page.getByRole('button', { name }).element() as HTMLElement;
			edge.focus();
			await view.rerender({ index });
			await expect.element(viewer()).toHaveFocus();
		}
	});

	it('arrow keys belong to the open More menu, not to the photos', async () => {
		server();
		const { onindex } = open();
		await page.getByRole('button', { name: 'More' }).click();
		await userEvent.keyboard('{ArrowRight}');
		expect(onindex).not.toHaveBeenCalled();
		await expect.element(page.getByRole('button', { name: 'Fix date' })).toBeInTheDocument();
		await userEvent.keyboard('{Escape}{ArrowRight}');
		expect(onindex.mock.calls).toEqual([[1]]);
	});
});

describe('Loupe: details and actions', () => {
	it('a change to the open photo keeps its details: no second fetch, the same buttons', async () => {
		const api = server();
		const { view } = open();
		const edit = page.getByRole('button', { name: 'Edit' });
		await expect.element(edit).toBeInTheDocument();
		const button = edit.element();
		await view.rerender({ items: [{ ...photos[0], favourite: true }, ...photos.slice(1)] });
		await expect
			.element(page.getByRole('button', { name: 'Favourite' }))
			.toHaveAttribute('aria-pressed', 'true');
		expect(button.isConnected).toBe(true);
		expect(api.count('GET', '/api/assets/1')).toBe(1);
		// Another photo: its own details.
		await view.rerender({ index: 1 });
		await vi.waitFor(() => expect(api.count('GET', '/api/assets/2')).toBe(1));
	});

	it('Pin to Home (under More) pins the photo for this account, and says so', async () => {
		const api = server();
		const release = api.hold('PATCH /api/assets/1/state');
		const { onchanged } = open();
		await page.getByRole('button', { name: 'More' }).click();
		await page.getByRole('button', { name: 'Pin to Home' }).click();
		expect(onchanged).toHaveBeenLastCalledWith({ ...photos[0], pinned: true });
		release({ ...photos[0], pinned: true });
		await vi.waitFor(() => expect(notice.text).toBe('Pinned to Home.'));
		expect(api.count('PATCH', '/api/assets/1/state')).toBe(1);
		notice.show('');
	});

	it('Favourite works on the next photo while the previous one is still being saved', async () => {
		const api = server();
		const release = api.hold('PATCH /api/assets/1/state');
		const { view, onchanged } = open();
		const favourite = page.getByRole('button', { name: 'Favourite' });
		await favourite.click();
		expect(onchanged).toHaveBeenLastCalledWith({ ...photos[0], favourite: true });
		// A second press on the same photo waits for the first.
		await favourite.click();
		expect(onchanged).toHaveBeenCalledOnce();
		await view.rerender({ index: 1 });
		await favourite.click();
		expect(onchanged).toHaveBeenLastCalledWith({ ...photos[1], favourite: true });
		await vi.waitFor(() => expect(api.count('PATCH', '/api/assets/2/state')).toBe(1));
		release({ ...photos[0], favourite: true });
	});

	it('details that come back for a photo no longer open are not shown', async () => {
		const api = server();
		const { view } = open();
		const readout = () => document.querySelector('.readout')!.textContent;
		await vi.waitFor(() => expect(readout()).toContain('Camera 1'));
		// Adding to an album asks for the photo's details again; that answer is slow.
		const release = api.hold('GET /api/assets/1');
		await page.getByRole('button', { name: 'Add to album', exact: true }).click();
		await page.getByRole('textbox', { name: 'New album title' }).fill('Nine');
		await page.getByRole('button', { name: 'Add', exact: true }).click();
		await vi.waitFor(() => expect(api.count('GET', '/api/assets/1')).toBe(2));
		await view.rerender({ index: 1 });
		await vi.waitFor(() => expect(readout()).toContain('Camera 2'));
		release(detailOf(photos[0], 'Late answer'));
		await wait(50);
		expect(readout()).toContain('Camera 2');
	});
});

describe('Loupe: Close and Details', () => {
	afterEach(() => page.viewport(414, 896));

	it('are round icons with no words, named for a screen reader and as a tooltip', async () => {
		server();
		open();
		for (const name of ['Close', 'Details', 'Zoom']) {
			const button = page.getByRole('button', { name, exact: true });
			await expect.element(button).toHaveAttribute('title', name);
			await expect.element(button).toHaveClass(/icon-button/);
			await expect.element(button).not.toHaveClass(/worded/);
		}
	});

	it('on a laptop the details sit beside the photo as label and value tiles, with who is in it', async () => {
		await page.viewport(1280, 800);
		server();
		const { view } = open();
		const details = page.getByRole('complementary', { name: 'Details' });
		await expect.element(details).toBeVisible();
		await expect
			.element(page.getByRole('button', { name: 'Details' }))
			.toHaveAttribute('aria-pressed', 'true');
		const labels = () =>
			[...details.element().querySelectorAll('.tile-row .k')].map((k) => k.textContent);
		await vi.waitFor(() => expect(labels()).toEqual(['Taken', 'Camera', 'From']));
		await view.rerender({ index: 1 });
		const sam = details.getByRole('link', { name: 'Sam' });
		await expect.element(sam).toHaveAttribute('href', '/people/5');
		expect(labels()).toEqual(['Taken', 'Camera', 'From', 'People']);
	});
});
