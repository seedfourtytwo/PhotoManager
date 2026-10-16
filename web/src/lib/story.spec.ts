import { describe, expect, it } from 'vitest';
import type { AssetPage } from './api/types';
import {
	PHOTO_MS,
	STORY_LIMIT,
	collect,
	fitFor,
	left,
	panFor,
	pause,
	resume,
	spread,
	start,
	step,
	type Clock
} from './story';
import { makeAsset } from './testing/fixtures';

const range = (n: number) => Array.from({ length: n }, (_, i) => i);

describe('spread: at most ~40 photos, evenly over the period', () => {
	it('keeps every photo when there are few', () => {
		expect(spread(range(5))).toEqual(range(5));
		expect(spread(range(STORY_LIMIT))).toEqual(range(STORY_LIMIT));
		expect(spread([])).toEqual([]);
	});
	it('takes evenly spaced ones from many, the first and the last included, in order', () => {
		const picked = spread(range(400));
		expect(picked).toHaveLength(STORY_LIMIT);
		expect(picked[0]).toBe(0);
		expect(picked.at(-1)).toBe(399);
		expect(new Set(picked).size).toBe(STORY_LIMIT);
		expect([...picked].sort((a, b) => a - b)).toEqual(picked);
		const gaps = picked.slice(1).map((n, i) => n - picked[i]);
		expect(Math.max(...gaps) - Math.min(...gaps)).toBeLessThanOrEqual(1);
	});
	it('one more than the limit still gives the limit, all different', () => {
		const picked = spread(range(STORY_LIMIT + 1));
		expect(picked).toHaveLength(STORY_LIMIT);
		expect(new Set(picked).size).toBe(STORY_LIMIT);
	});
	it('takes a smaller limit too', () => {
		expect(spread(range(10), 3)).toEqual([0, 5, 9]);
		expect(spread(range(10), 1)).toEqual([0]);
	});
});

describe('the clock of a story', () => {
	const at = (clock: Clock | null) =>
		clock && { index: clock.index, running: clock.since !== null };

	it('starts on the first photo, running, a whole photo’s time left', () => {
		const clock = start(3, 1000);
		expect(at(clock)).toEqual({ index: 0, running: true });
		expect(left(clock, 1000)).toBe(PHOTO_MS);
		expect(left(clock, 1000 + 1200)).toBe(PHOTO_MS - 1200);
		expect(left(clock, 1000 + PHOTO_MS + 500)).toBe(0);
		expect(PHOTO_MS).toBeGreaterThanOrEqual(3000);
		expect(PHOTO_MS).toBeLessThanOrEqual(3500);
	});

	it('a pause holds the time left, however long it lasts; resuming goes on from there', () => {
		const paused = pause(start(3, 0), 1000);
		expect(at(paused)).toEqual({ index: 0, running: false });
		expect(left(paused, 60_000)).toBe(PHOTO_MS - 1000);
		const resumed = resume(paused, 60_000);
		expect(left(resumed, 60_500)).toBe(PHOTO_MS - 1500);
	});

	it('pausing twice or resuming a running clock changes nothing', () => {
		const paused = pause(start(3, 0), 1000);
		expect(pause(paused, 2000)).toEqual(paused);
		const running = start(3, 0);
		expect(resume(running, 2000)).toEqual(running);
	});

	it('next shows the following photo from its start', () => {
		const next = step(start(3, 0), 1, 2000);
		expect(at(next)).toEqual({ index: 1, running: true });
		expect(left(next!, 2000)).toBe(PHOTO_MS);
	});

	it('next after the last photo ends the story', () => {
		const last = step(step(start(3, 0), 1, 10)!, 1, 20)!;
		expect(last.index).toBe(2);
		expect(step(last, 1, 30)).toBeNull();
	});

	it('previous goes one back; on the first photo it starts that one again', () => {
		const second = step(start(3, 0), 1, 10)!;
		expect(at(step(second, -1, 20))).toEqual({ index: 0, running: true });
		const first = start(3, 0);
		const again = step(first, -1, 2500)!;
		expect(again.index).toBe(0);
		expect(left(again, 2500)).toBe(PHOTO_MS);
	});

	it('a step while paused stays paused, a whole photo’s time left', () => {
		const paused = pause(start(3, 0), 1000);
		const next = step(paused, 1, 5000)!;
		expect(at(next)).toEqual({ index: 1, running: false });
		expect(left(next, 90_000)).toBe(PHOTO_MS);
	});

	it('a story of no photos has nothing to show', () => {
		expect(step(start(0, 0), 1, 0)).toBeNull();
	});
});

describe('collect: the photos of a period, oldest first', () => {
	const pages: AssetPage[] = [
		{ items: [makeAsset(5), makeAsset(4)], next_cursor: 'a' },
		{ items: [makeAsset(3), makeAsset(2)], next_cursor: 'b' },
		{ items: [makeAsset(1)], next_cursor: null }
	];
	const timeline = () => {
		const asked: (string | null)[] = [];
		const ask = async (cursor: string | null) => {
			asked.push(cursor);
			return pages[asked.length - 1];
		};
		return { asked, ask };
	};

	it('pages through the timeline (newest first) and gives it back oldest first', async () => {
		const { asked, ask } = timeline();
		const all = await collect(ask);
		expect(all.map((a) => a.id)).toEqual([1, 2, 3, 4, 5]);
		expect(asked).toEqual([null, 'a', 'b']);
	});

	it('stops after the pages it may ask for', async () => {
		const { asked, ask } = timeline();
		const some = await collect(ask, 2);
		expect(some.map((a) => a.id)).toEqual([2, 3, 4, 5]);
		expect(asked).toEqual([null, 'a']);
	});
});

describe('fitFor: a photo fills the screen when it has its shape, else shows whole', () => {
	it.each([
		[1.5, 16 / 9, 'cover'],
		[0.75, 390 / 844, 'cover'],
		[1.5, 390 / 844, 'contain'],
		[0.75, 16 / 9, 'contain'],
		[1, 1.6, 'contain']
	] as const)('a %d photo on a %d screen: %s', (photo, screen, fit) => {
		expect(fitFor(photo, screen)).toBe(fit);
	});
});

describe('panFor: each photo moves its own way, the same each time', () => {
	it('four moves in turn, by its place in the story', () => {
		expect([0, 1, 2, 3, 4].map(panFor)).toEqual(['in', 'out', 'left', 'right', 'in']);
	});
});
