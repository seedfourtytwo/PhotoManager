import { page, userEvent } from 'vitest/browser';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import type { AssetDetail, AssetOut } from '$lib/api';
import { session } from '$lib/app.svelte';
import { makeAsset } from '$lib/testing/fixtures';
import Loupe from './Loupe.svelte';

const pixel = 'data:image/gif;base64,R0lGODlhAQABAAAAACw=';
const photos = [1, 2, 3].map((id) =>
	makeAsset(id, `2019-07-0${id}T10:00:00`, 400, 300, { thumb: { url: pixel } })
);
const detailOf = (asset: AssetOut, camera = `Camera ${asset.id}`): AssetDetail => ({
	...asset,
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

type Call = { method: string; path: string };
/** Every request the viewer made; `hold(path)` keeps the next answer for it back until released. */
function server() {
	const calls: Call[] = [];
	const held = new Map<string, Promise<unknown>>();
	const answer = (method: string, path: string): unknown => {
		const asset = photos.find((a) => path.startsWith(`/api/assets/${a.id}`));
		if (path === '/api/albums') return method === 'GET' ? [] : { id: 9, title: 'Nine' };
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
		finger('pointermove', -150);
		// A pinch does not pull the photo along either.
		expect(document.querySelector('.stage')!.classList.contains('held')).toBe(false);
		finger('pointerup', -150, { pointerId: 2 });
		// One finger of the pinch is still down: nothing starts with a third touch.
		finger('pointerdown', 0, { pointerId: 3 });
		finger('pointerup', 0, { pointerId: 3, clientY: 400 });
		finger('pointerup', -150);
		expect(onindex).not.toHaveBeenCalled();
		expect(onclose).not.toHaveBeenCalled();
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
		await page.getByRole('button', { name: 'Album', exact: true }).click();
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
