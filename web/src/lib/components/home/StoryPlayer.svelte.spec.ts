import { tick } from 'svelte';
import { page, userEvent } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import type { AssetOut } from '$lib/api';
import { PHOTO_MS } from '$lib/story';
import { makeAsset } from '$lib/testing/fixtures';
import StoryPlayer from './StoryPlayer.svelte';

const photos = [1, 2, 3].map((id) => makeAsset(id, `2024-07-1${id}T10:00:00`));
const poster = photos[1];

function play(list: AssetOut[] | null = photos) {
	const onclose = vi.fn();
	const view = render(StoryPlayer, {
		title: 'Lisbon, July 2024',
		dates: '12 to 19 July 2024',
		photos: list,
		poster,
		onclose
	});
	return { onclose, view };
}

const player = () => page.getByRole('dialog', { name: 'Lisbon, July 2024' });
/** Which photo is on top of the stage. */
const shown = () => {
	const all = document.querySelectorAll<HTMLImageElement>('.story .photo');
	return Number(/assets\/(\d+)\/preview/.exec(all[all.length - 1]?.src ?? '')?.[1]);
};
const segments = () => document.querySelectorAll('.story .segment').length;
/** A button pressed straight in the page: Playwright's clicks wait on timers the clock holds. */
const press = (name: string) =>
	document.querySelector<HTMLElement>(`[aria-label="${name}"]`)!.click();

afterEach(() => {
	vi.useRealTimers();
	Reflect.deleteProperty(document, 'visibilityState');
});

describe('StoryPlayer', () => {
	it('shows the poster, the title and the dates while the photos come; Close closes', async () => {
		const { onclose } = play(null);
		await expect.element(player()).toBeVisible();
		await expect.element(player().getByText('12 to 19 July 2024')).toBeVisible();
		expect(shown()).toBe(2);
		expect(segments()).toBe(0);
		await page.getByRole('button', { name: 'Close' }).click();
		expect(onclose).toHaveBeenCalled();
	});

	it('one progress segment per photo; tap right for the next, left for the previous', async () => {
		const { onclose } = play();
		await expect.element(player()).toBeVisible();
		expect(segments()).toBe(3);
		expect(shown()).toBe(1);
		await page.getByRole('button', { name: 'Next photo' }).click();
		expect(shown()).toBe(2);
		await page.getByRole('button', { name: 'Previous photo' }).click();
		expect(shown()).toBe(1);
		await page.getByRole('button', { name: 'Previous photo' }).click();
		expect(shown()).toBe(1);
		expect(onclose).not.toHaveBeenCalled();
	});

	it('the next one after the last photo closes the story', async () => {
		const { onclose } = play();
		for (let i = 0; i < 2; i++) await page.getByRole('button', { name: 'Next photo' }).click();
		expect(shown()).toBe(3);
		expect(onclose).not.toHaveBeenCalled();
		await page.getByRole('button', { name: 'Next photo' }).click();
		expect(onclose).toHaveBeenCalled();
	});

	it('goes on by itself, each photo for its time, and closes after the last', async () => {
		vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
		const { onclose } = play();
		await tick();
		expect(shown()).toBe(1);
		vi.advanceTimersByTime(PHOTO_MS - 10);
		await tick();
		expect(shown()).toBe(1);
		vi.advanceTimersByTime(10);
		await tick();
		expect(shown()).toBe(2);
		vi.advanceTimersByTime(PHOTO_MS);
		await tick();
		expect(shown()).toBe(3);
		vi.advanceTimersByTime(PHOTO_MS);
		await tick();
		expect(onclose).toHaveBeenCalled();
	});

	it('Pause holds it where it is; Play goes on with the time it had left', async () => {
		vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
		play();
		await tick();
		vi.advanceTimersByTime(1000);
		press('Pause');
		await tick();
		expect(document.querySelector('[aria-label="Play"]')).not.toBeNull();
		vi.advanceTimersByTime(60_000);
		await tick();
		expect(shown()).toBe(1);
		press('Play');
		await tick();
		vi.advanceTimersByTime(PHOTO_MS - 1000);
		await tick();
		expect(shown()).toBe(2);
	});

	it('stands still while the page is hidden', async () => {
		vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
		play();
		await tick();
		const visibility = (state: DocumentVisibilityState) => {
			Object.defineProperty(document, 'visibilityState', { value: state, configurable: true });
			document.dispatchEvent(new Event('visibilitychange'));
		};
		visibility('hidden');
		await tick();
		vi.advanceTimersByTime(60_000);
		await tick();
		expect(shown()).toBe(1);
		visibility('visible');
		await tick();
		vi.advanceTimersByTime(PHOTO_MS);
		await tick();
		expect(shown()).toBe(2);
	});

	it('the arrow keys step through it, and Escape closes it', async () => {
		const { onclose } = play();
		await expect.element(player()).toBeVisible();
		await userEvent.keyboard('{ArrowRight}');
		expect(shown()).toBe(2);
		await userEvent.keyboard('{ArrowLeft}');
		expect(shown()).toBe(1);
		await userEvent.keyboard('{Escape}');
		expect(onclose).toHaveBeenCalled();
	});

	it('pulled down far enough it closes; a short slow pull springs back and steps nothing', async () => {
		const { onclose } = play();
		await expect.element(player()).toBeVisible();
		const stage = document.querySelector<HTMLElement>('.story .stage')!;
		const finger = (type: string, y: number) =>
			stage.dispatchEvent(
				new PointerEvent(type, { bubbles: true, pointerId: 7, button: 0, clientX: 200, clientY: y })
			);
		finger('pointerdown', 100);
		finger('pointermove', 140);
		await tick();
		expect(stage.style.transform).toBe('translateY(40px)');
		await new Promise((done) => setTimeout(done, 250));
		finger('pointerup', 140);
		await tick();
		expect(onclose).not.toHaveBeenCalled();
		expect(stage.style.transform).toBe('');
		expect(shown()).toBe(1);

		finger('pointerdown', 100);
		finger('pointermove', 400);
		finger('pointerup', 400);
		expect(onclose).toHaveBeenCalled();
	});

	it('a press held on the photo pauses it, and letting go does not step', async () => {
		play();
		await expect.element(player()).toBeVisible();
		const next = document.querySelector<HTMLElement>('[aria-label="Next photo"]')!;
		const finger = (type: string) =>
			next.dispatchEvent(
				new PointerEvent(type, {
					bubbles: true,
					pointerId: 3,
					button: 0,
					clientX: 300,
					clientY: 300
				})
			);
		finger('pointerdown');
		await tick();
		expect(document.querySelector('.story.still')).not.toBeNull();
		await new Promise((done) => setTimeout(done, 450));
		finger('pointerup');
		next.click();
		await tick();
		expect(shown()).toBe(1);
		expect(document.querySelector('.story.still')).toBeNull();
		next.click(); // a plain tap again
		await tick();
		expect(shown()).toBe(2);
	});
});
