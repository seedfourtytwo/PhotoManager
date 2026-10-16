import { page, userEvent } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import type { Person, Portrait } from '$lib/api';
import { nudge, pan } from '$lib/portrait';
import PortraitDialog from './PortraitDialog.svelte';

type Sent = { method: string; url: string; body: unknown };

const face = (face_id: number, extra: Partial<Portrait> = {}): Portrait => ({
	face_id,
	asset_id: face_id * 10,
	cx: 0.5,
	cy: 0.4,
	size: 0.5,
	chosen: false,
	// A picture that loads: one that fails is taken away again, which a slow machine sees.
	url: `data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==#${face_id}`,
	...extra
});
const FACES = [face(1), face(2), face(3)];

const lea = (portrait: Portrait): Person => ({
	id: 7,
	name: 'Léa',
	face_count: 3,
	asset_count: 3,
	hidden: false,
	cover: null,
	portrait: { ...portrait, url: '/api/people/7/portrait?v=now' }
});

function open(person: Person) {
	const sent: Sent[] = [];
	const answer = { ...person, name: 'Answered' };
	vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
		const url = String(input);
		const method = init?.method ?? 'GET';
		sent.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
		return new Response(JSON.stringify(method === 'GET' ? FACES : answer), {
			headers: { 'content-type': 'application/json' }
		});
	});
	const onclose = vi.fn();
	const onsaved = vi.fn();
	render(PortraitDialog, { person, onclose, onsaved });
	return { sent, onclose, onsaved, answer };
}

const stage = () => page.getByRole('group', { name: /^Portrait/ });
const photo = (n: number) => page.getByRole('button', { name: `Photo ${n}`, exact: true });

/** The photo under the window has loaded: a 4:3 picture (no server here to send one). */
async function photoLoaded(width = 400, height = 300) {
	await expect.element(stage()).toBeInTheDocument();
	const img = stage().element().querySelector('img')!;
	Object.defineProperty(img, 'naturalWidth', { value: width, configurable: true });
	Object.defineProperty(img, 'naturalHeight', { value: height, configurable: true });
	img.dispatchEvent(new Event('load'));
	await expect.element(page.getByRole('button', { name: 'Save' })).toBeEnabled();
}

/** The stage, taking pointer events made here: only a real pointer can be captured. */
function grabbable() {
	const el = stage().element() as HTMLElement;
	el.setPointerCapture = () => {};
	return el;
}

afterEach(() => vi.unstubAllGlobals());

describe('PortraitDialog', () => {
	it('offers the person’s faces, the one in use marked, over that photo without its edits', async () => {
		const { sent } = open(lea(face(2, { chosen: true, size: 0.3 })));
		await expect.element(photo(2)).toHaveAttribute('aria-pressed', 'true');
		await expect.element(photo(1)).toHaveAttribute('aria-pressed', 'false');
		await expect.element(photo(3)).toBeInTheDocument();
		expect(sent[0]).toMatchObject({ method: 'GET', url: '/api/people/7/faces?limit=24' });
		// The pictures come a moment after the buttons: wait for them, do not assume them.
		const src = (within: Element) => within.querySelector('img')?.getAttribute('src');
		await vi.waitFor(() => {
			expect(src(stage().element())).toBe('/api/assets/20/preview?edit=none');
			expect(src(photo(1).element())).toBe(FACES[0].url);
		});
	});

	it('saves the photo that was picked and the circle as it was moved and zoomed', async () => {
		const { sent, onsaved, answer } = open(lea(face(1)));
		await photo(3).click();
		await expect.element(photo(3)).toHaveAttribute('aria-pressed', 'true');
		await photoLoaded();
		(stage().element() as HTMLElement).focus();
		await userEvent.keyboard('{+}{+}{ArrowLeft}');
		await page.getByRole('button', { name: 'Save' }).click();
		await vi.waitFor(() => expect(onsaved).toHaveBeenCalledWith(answer));

		const aspect = 4 / 3;
		const start = { cx: 0.5, cy: 0.4, size: 0.5 };
		const expected = ['+', '+', 'ArrowLeft'].reduce((c, key) => nudge(c, key, aspect)!, start);
		expect(expected.size).toBeLessThan(0.5);
		const put = sent.at(-1)!;
		expect(put).toMatchObject({ method: 'PUT', url: '/api/people/7/portrait' });
		const body = put.body as { face_id: number; cx: number; cy: number; size: number };
		expect(body.face_id).toBe(3);
		expect(body.cx).toBeCloseTo(expected.cx);
		expect(body.cy).toBeCloseTo(expected.cy);
		expect(body.size).toBeCloseTo(expected.size);
	});

	it('starts each other photo on its own automatic circle, and the one in use where it was left', async () => {
		const { sent } = open(lea(face(2, { chosen: true, cx: 0.3, cy: 0.6, size: 0.3 })));
		await photoLoaded();
		await photo(1).click();
		await photoLoaded();
		await photo(2).click();
		await photoLoaded();
		await page.getByRole('button', { name: 'Save' }).click();
		await vi.waitFor(() => expect(sent.at(-1)!.method).toBe('PUT'));
		expect(sent.at(-1)!.body).toEqual({ face_id: 2, cx: 0.3, cy: 0.6, size: 0.3 });
	});

	it('drags the photo under the window with the pointer', async () => {
		const { sent } = open(lea(face(1)));
		await photoLoaded();
		const el = grabbable();
		const box = el.getBoundingClientRect();
		const at = (dx: number, dy: number) => ({
			pointerId: 1,
			button: 0,
			isPrimary: true,
			bubbles: true,
			clientX: box.left + box.width / 2 + dx,
			clientY: box.top + box.height / 2 + dy
		});
		el.dispatchEvent(new PointerEvent('pointerdown', at(0, 0)));
		el.dispatchEvent(new PointerEvent('pointermove', at(box.width / 10, -box.height / 5)));
		el.dispatchEvent(new PointerEvent('pointerup', at(box.width / 10, -box.height / 5)));
		await page.getByRole('button', { name: 'Save' }).click();
		await vi.waitFor(() => expect(sent.at(-1)!.method).toBe('PUT'));

		const expected = pan({ cx: 0.5, cy: 0.4, size: 0.5 }, 0.1, -0.2, 4 / 3);
		const body = sent.at(-1)!.body as { cx: number; cy: number; size: number };
		expect(body.cx).toBeCloseTo(expected.cx);
		expect(body.cy).toBeCloseTo(expected.cy);
		expect(body.size).toBe(0.5);
	});

	it('zooms in when two fingers move apart, about the point between them', async () => {
		const { sent } = open(lea(face(1)));
		await photoLoaded();
		const el = grabbable();
		const box = el.getBoundingClientRect();
		const finger = (pointerId: number, dx: number) => ({
			pointerId,
			button: 0,
			bubbles: true,
			clientX: box.left + box.width / 2 + dx,
			clientY: box.top + box.height / 2
		});
		el.dispatchEvent(new PointerEvent('pointerdown', finger(1, -20)));
		el.dispatchEvent(new PointerEvent('pointerdown', finger(2, 20)));
		el.dispatchEvent(new PointerEvent('pointermove', finger(1, -40)));
		el.dispatchEvent(new PointerEvent('pointermove', finger(2, 40)));
		el.dispatchEvent(new PointerEvent('pointerup', finger(1, -40)));
		el.dispatchEvent(new PointerEvent('pointerup', finger(2, 40)));
		await page.getByRole('button', { name: 'Save' }).click();
		await vi.waitFor(() => expect(sent.at(-1)!.method).toBe('PUT'));
		const body = sent.at(-1)!.body as { cx: number; cy: number; size: number };
		expect(body.size).toBeCloseTo(0.25);
		expect(body.cx).toBeCloseTo(0.5);
		expect(body.cy).toBeCloseTo(0.4);
	});

	it('has no zoom slider: pinch, wheel and the + and − keys zoom', async () => {
		open(lea(face(1)));
		await photoLoaded();
		expect(page.getByRole('slider').elements()).toHaveLength(0);
	});

	it('a double tap goes back to the face as it was found', async () => {
		const { sent } = open(lea(face(1)));
		await photoLoaded();
		await stage().click();
		await userEvent.keyboard('++{ArrowRight}');
		(stage().element() as HTMLElement).dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
		await page.getByRole('button', { name: 'Save' }).click();
		await vi.waitFor(() => expect(sent.at(-1)!.method).toBe('PUT'));
		const body = sent.at(-1)!.body as { cx: number; cy: number; size: number };
		const found = face(1);
		expect(body.size).toBeCloseTo(found.size);
		expect(body.cx).toBeCloseTo(found.cx);
		expect(body.cy).toBeCloseTo(found.cy);
	});

	it('“Use automatic” clears the choice; there is nothing to clear without one', async () => {
		const chosen = open(lea(face(2, { chosen: true })));
		await page.getByRole('button', { name: 'Use automatic' }).click();
		await vi.waitFor(() => expect(chosen.onsaved).toHaveBeenCalledWith(chosen.answer));
		expect(chosen.sent.at(-1)).toMatchObject({ method: 'DELETE', url: '/api/people/7/portrait' });
	});

	it('does not offer “Use automatic” while the portrait is the automatic one', async () => {
		open(lea(face(1)));
		await expect.element(page.getByRole('button', { name: 'Use automatic' })).toBeDisabled();
	});
});
