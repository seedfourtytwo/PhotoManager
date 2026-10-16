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

function open(items = photos, index = 0, extra: { onremove?: (ids: Set<number>) => void } = {}) {
	const handlers = { onindex: vi.fn(), onclose: vi.fn(), onchanged: vi.fn() };
	const view = render(Loupe, { items, index, ...handlers, ...extra });
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
const idle = () => expect.element(viewer(), { timeout: 5000 }).toHaveClass(/hidden/);
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
		// A pinch does not pull the photos along either.
		expect(document.querySelector<HTMLElement>('.track')!.style.transform).toBe('');
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
		// Said once the next photo has slid into place.
		expect(onindex).not.toHaveBeenCalled();
		await expect.poll(() => onindex.mock.calls).toEqual([[1]]);
	});

	it('a viewer closed while the next photo slides in does not step to it', async () => {
		server();
		const { finger, onindex, view } = open();
		finger('pointerdown');
		finger('pointerup', -150);
		view.unmount();
		await wait(800);
		expect(onindex).not.toHaveBeenCalled();
	});

	it('only the main button is a press: a right click leaves the chrome alone', async () => {
		server();
		const { finger } = open();
		finger('pointerdown', 0, { pointerType: 'mouse', button: 2 });
		finger('pointerup', 0, { pointerType: 'mouse', button: 2 });
		await wait(400);
		await expect.element(viewer()).not.toHaveClass(/hidden/);
	});
});

describe('Loupe: steps slide', () => {
	const five = [1, 2, 3, 4, 5].map((id) =>
		makeAsset(id, `2019-07-0${id}T10:00:00`, 400, 300, { thumb: { url: pixel } })
	);
	/** The viewer as a page has it: the index follows what it says. */
	function follow(items = five, index = 0) {
		const onindex = vi.fn((i: number) => void view.rerender({ index: i }));
		const view = render(Loupe, { items, index, onindex, onclose: vi.fn(), onchanged: vi.fn() });
		return { onindex, view };
	}
	const track = () => document.querySelector<HTMLElement>('.track')!;
	/** Where the track is drawn, in px from the open photo at rest. */
	const shift = () => new DOMMatrix(getComputedStyle(track()).transform).m41;
	const stage = () => document.querySelector<HTMLElement>('.stage')!;
	const wheel = (deltaX: number, deltaY = 0, extra: WheelEventInit = {}) => {
		const event = new WheelEvent('wheel', {
			deltaX,
			deltaY,
			bubbles: true,
			cancelable: true,
			...extra
		});
		stage().dispatchEvent(event);
		return event;
	};
	/** A two-finger swipe on a trackpad: `n` wheel events of `dx` each, 16 ms apart. */
	async function swipe(dx: number, n: number) {
		for (let i = 0; i < n; i++) {
			wheel(dx);
			await wait(16);
		}
	}

	it('an arrow key slides the next photo in and opens it once it has arrived', async () => {
		server();
		const { onindex } = follow();
		await userEvent.keyboard('{ArrowRight}');
		expect(onindex).not.toHaveBeenCalled();
		// On its way: neither photo is where it rests.
		await expect.poll(shift).toBeLessThan(-5);
		expect(shift()).toBeGreaterThan(-stage().clientWidth);
		await expect.poll(() => onindex.mock.calls).toEqual([[1]]);
		await expect.poll(shift).toBe(0);
	});

	it('the edge buttons slide the same way', async () => {
		server();
		const { onindex } = follow(five, 2);
		// A component test has no page styles: the round button is a dot, clicked as the DOM does.
		(page.getByRole('button', { name: 'Previous photo' }).element() as HTMLElement).click();
		expect(onindex).not.toHaveBeenCalled();
		await expect.poll(shift).toBeGreaterThan(5);
		await expect.poll(() => onindex.mock.calls).toEqual([[1]]);
	});

	it('quick presses land on the photo they count to, each turn said once', async () => {
		server();
		const { onindex } = follow();
		await userEvent.keyboard('{ArrowRight}{ArrowRight}{ArrowRight}');
		await expect.poll(() => onindex.mock.calls.at(-1)).toEqual([3]);
		await wait(600);
		expect(onindex.mock.calls).toEqual([[1], [2], [3]]);
		expect(shift()).toBe(0);
	});

	it('a press back the other way before it arrives goes home: no step', async () => {
		server();
		const { onindex } = follow(five, 2);
		await userEvent.keyboard('{ArrowRight}{ArrowLeft}');
		await wait(700);
		expect(onindex).not.toHaveBeenCalled();
		expect(shift()).toBe(0);
	});

	it('presses past the last photo stop on it', async () => {
		server();
		const { onindex } = follow(five, 3);
		await userEvent.keyboard('{ArrowRight}{ArrowRight}{ArrowRight}');
		await wait(900);
		expect(onindex.mock.calls).toEqual([[4]]);
		expect(shift()).toBe(0);
	});

	it('under reduced motion a step jumps at once', async () => {
		server();
		const real = window.matchMedia.bind(window);
		vi.stubGlobal('matchMedia', (query: string) =>
			query.includes('reduced-motion')
				? ({ matches: true, media: query } as MediaQueryList)
				: real(query)
		);
		const { onindex } = follow();
		await userEvent.keyboard('{ArrowRight}');
		expect(onindex.mock.calls).toEqual([[1]]);
		expect(shift()).toBe(0);
	});

	it('a two-finger swipe on a trackpad drags the photos and turns past a third of the width', async () => {
		server();
		const { onindex } = follow();
		const step = Math.ceil((stage().clientWidth * 0.4) / 10);
		await swipe(step, 10);
		// Dragged, not yet turned: the trackpad is still down.
		expect(shift()).toBeLessThan(-step * 5);
		expect(onindex).not.toHaveBeenCalled();
		await expect.poll(() => onindex.mock.calls).toEqual([[1]]);
		await expect.poll(shift).toBe(0);
	});

	it('a short trackpad swipe springs back', async () => {
		server();
		const { onindex } = follow(five, 1);
		await swipe(-4, 5);
		await expect.poll(shift).toBe(0);
		await wait(300);
		expect(onindex).not.toHaveBeenCalled();
	});

	it('the momentum after a swipe that turned does not turn again', async () => {
		server();
		const { onindex } = follow();
		await swipe(Math.ceil((stage().clientWidth * 0.4) / 10), 10);
		await wait(150);
		// The trackpad's own momentum, dying away, still coming in.
		for (let dx = 30; dx > 0; dx -= 2) {
			wheel(dx);
			await wait(16);
		}
		await wait(700);
		expect(onindex.mock.calls).toEqual([[1]]);
	});

	it("a vertical scroll and a pinch (ctrl + wheel) are not the stage's", async () => {
		server();
		const { onindex } = follow();
		for (let i = 0; i < 10; i++) {
			expect(wheel(2, 40).defaultPrevented).toBe(false);
			expect(wheel(40, 0, { ctrlKey: true }).defaultPrevented).toBe(false);
		}
		await wait(300);
		expect(onindex).not.toHaveBeenCalled();
		expect(shift()).toBe(0);
		// A sideways one is: the browser does not go Back under it.
		expect(wheel(40).defaultPrevented).toBe(true);
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
		// Without the page's styles the zoom level pill lies over the button: clicked as the DOM does.
		(zoomButton().element() as HTMLElement).click();
		await tick();
		expect(zoom()).toBe(1);
	});

	it('zooming in puts the chrome away; back at the fit it returns', async () => {
		server();
		const { finger } = open();
		doubleTap(finger);
		await expect.element(viewer()).toHaveClass(/hidden/);
		doubleTap(finger);
		await expect.element(viewer()).not.toHaveClass(/hidden/);
	});
});

describe('Loupe: chrome', () => {
	it('a tap on the photo fades all the chrome, the edges and the shade; the next brings it back', async () => {
		server();
		const { finger } = open();
		await expect.element(viewer()).not.toHaveClass(/hidden/);
		finger('pointerdown');
		finger('pointerup');
		await expect.element(viewer()).toHaveClass(/hidden/);
		// Wait out the double tap: the next tap is a tap of its own.
		await wait(400);
		finger('pointerdown');
		finger('pointerup');
		await expect.element(viewer()).not.toHaveClass(/hidden/);
		expect(document.querySelectorAll('.scrim')).toHaveLength(2);
	});

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
		await expect.element(viewer()).not.toHaveClass(/hidden/);
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
		await expect.element(viewer()).not.toHaveClass(/hidden/);
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
		await expect.poll(() => onindex.mock.calls).toEqual([[1]]);
	});
});

describe('Loupe: details and actions', () => {
	it('a change to the open photo keeps its details: no second fetch, the same buttons', async () => {
		const api = server();
		const { view } = open();
		await vi.waitFor(() => expect(api.count('GET', '/api/assets/1')).toBe(1));
		const button = page.getByRole('button', { name: 'Add to album' }).element();
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
		await page.getByRole('button', { name: 'Details', exact: true }).click();
		const camera = () => document.querySelector('.details .model')?.textContent ?? '';
		// The sheet's state outlives this viewer: it is closed again at the end.
		await vi.waitFor(() => expect(camera()).toContain('Camera 1'));
		// Adding to an album asks for the photo's details again; that answer is slow.
		const release = api.hold('GET /api/assets/1');
		await page.getByRole('button', { name: 'Add to album', exact: true }).click();
		await page.getByRole('textbox', { name: 'New album title' }).fill('Nine');
		await page.getByRole('button', { name: 'Add', exact: true }).click();
		await vi.waitFor(() => expect(api.count('GET', '/api/assets/1')).toBe(2));
		await view.rerender({ index: 1 });
		await vi.waitFor(() => expect(camera()).toContain('Camera 2'));
		release(detailOf(photos[0], 'Late answer'));
		await wait(50);
		expect(camera()).toContain('Camera 2');
		await page.getByRole('button', { name: 'Details', exact: true }).click();
		await expect.element(page.getByRole('complementary')).not.toBeInTheDocument();
	});

	it('Move to trash trashes the photo, moves on to the next one, and offers Undo', async () => {
		const api = server();
		const onremove = vi.fn();
		const { onindex, onclose } = open(photos, 1, { onremove });
		await page.getByRole('button', { name: 'Move to trash' }).click();
		await vi.waitFor(() => expect(onremove).toHaveBeenCalledWith(new Set([2])));
		expect(api.calls).toContainEqual({ method: 'DELETE', path: '/api/assets' });
		expect(onindex).toHaveBeenCalledWith(2);
		expect(onclose).not.toHaveBeenCalled();
		expect(notice.text).toBe('Moved to the trash.');
		notice.show('');
	});

	it('the last photo trashed steps back to the one before; the only one closes the viewer', async () => {
		server();
		const last = open(photos, 2, { onremove: vi.fn() });
		await page.getByRole('button', { name: 'Move to trash' }).click();
		await vi.waitFor(() => expect(last.onindex).toHaveBeenCalledWith(1));
		last.view.unmount();
		const only = open([photos[0]], 0, { onremove: vi.fn() });
		await page.getByRole('button', { name: 'Move to trash' }).click();
		await vi.waitFor(() => expect(only.onclose).toHaveBeenCalledOnce());
		notice.show('');
	});

	it('a page that cannot drop a photo has no Move to trash', async () => {
		server();
		open();
		// The photo may be edited (Edit is under More once its details are in) ...
		await page.getByRole('button', { name: 'More' }).click();
		await expect.element(page.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
		// ... but this page has no way to drop it.
		await expect
			.element(page.getByRole('button', { name: 'Move to trash' }))
			.not.toBeInTheDocument();
	});
});

describe('Loupe: the title', () => {
	it('reads the day, then the time and the place, at the top; said in words with pauses', async () => {
		const api = server();
		const place = { country: 'France', region: null, city: 'Nice' };
		open([{ ...photos[0], place }]);
		const title = document.querySelector<HTMLElement>('.title')!;
		expect(title.querySelector('.day')!.textContent).toBe('1 July 2019');
		expect([...title.querySelectorAll('.line span')].map((s) => s.textContent)).toEqual([
			'10:00',
			'Nice'
		]);
		expect(title.querySelector('.visually-hidden')!.textContent).toBe('1 July 2019, 10:00, Nice');
		expect(title.textContent).not.toContain('·');
		// The camera is in the details, never on the chrome.
		await vi.waitFor(() => expect(api.count('GET', '/api/assets/1')).toBe(1));
		await tick();
		expect(document.querySelector('.chrome')!.textContent).not.toContain('Camera 1');
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

	it('on a laptop the details are closed until asked for, then a panel of grouped cards with who is in it', async () => {
		await page.viewport(1280, 800);
		server();
		const { view } = open();
		const details = page.getByRole('complementary', { name: 'Details' });
		await expect.element(details).not.toBeInTheDocument();
		const info = page.getByRole('button', { name: 'Details' });
		await expect.element(info).toHaveAttribute('aria-pressed', 'false');
		await info.click();
		await expect.element(details).toBeVisible();
		await expect.element(info).toHaveAttribute('aria-pressed', 'true');
		const cards = () =>
			[...details.element().querySelectorAll('.card')].map(
				(card) => card.getAttribute('aria-label') ?? card.querySelector('h3, summary')?.textContent
			);
		// An admin also reads the file, closed until asked for.
		await vi.waitFor(() => expect(cards()).toEqual(['When and where', 'Camera', 'File']));
		// No loose line of key hints: those are under More, "Keyboard shortcuts".
		expect(details.element().textContent).not.toMatch(/Esc|← →/);
		await view.rerender({ index: 1 });
		const sam = details.getByRole('link', { name: 'Sam' });
		await expect.element(sam).toHaveAttribute('href', '/people/5');
		expect(cards()).toEqual(['When and where', 'People', 'Camera', 'File']);
		await userEvent.keyboard('i');
		await expect.element(details).not.toBeInTheDocument();
	});
});
