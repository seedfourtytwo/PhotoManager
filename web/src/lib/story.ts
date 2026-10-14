/**
 * The story player's steps and clock (spec 2026-10-14 §9), apart from the screen: photos one
 * after another, each for PHOTO_MS; next after the last ends the story, previous on the first
 * starts it again; a pause (a finger held down, the page hidden, the Pause button) holds the
 * time left. StoryPlayer.svelte draws it and keeps one timer to `left()`.
 */
import type { AssetOut, AssetPage } from './api/types';

/** How long each photo stays. */
export const PHOTO_MS = 3200;
/** About this many photos make a story: more is a slideshow, not a memory. */
export const STORY_LIMIT = 40;
/** A period's photos are fetched this many pages of the timeline deep (500 a page). */
const PAGES = 4;

/** At most `limit` items, spread evenly from the first to the last (both kept), in order. */
export function spread<T>(items: readonly T[], limit = STORY_LIMIT): T[] {
	if (items.length <= limit) return [...items];
	if (limit <= 1) return items.slice(0, limit);
	// More items than picks: neighbouring picks are over one apart, so rounding never repeats one.
	const gap = (items.length - 1) / (limit - 1);
	return Array.from({ length: limit }, (_, i) => items[Math.round(i * gap)]);
}

/**
 * Every photo of a period as far as `pages` pages of the timeline reach (a period of more
 * photos than that keeps its newest), oldest first, as a story is told.
 */
export async function collect(
	ask: (cursor: string | null) => Promise<AssetPage>,
	pages = PAGES
): Promise<AssetOut[]> {
	const all: AssetOut[] = [];
	let cursor: string | null = null;
	for (let page = 0; page < pages; page++) {
		const answer: AssetPage = await ask(cursor);
		all.push(...answer.items);
		cursor = answer.next_cursor;
		if (!cursor) break;
	}
	return all.reverse();
}

export type Clock = {
	/** The photo shown. */
	index: number;
	count: number;
	/** How long the photo was shown before it last started or resumed. */
	shown: number;
	/** When it last started or resumed; null while paused. */
	since: number | null;
};

export const start = (count: number, now: number): Clock => ({
	index: 0,
	count,
	shown: 0,
	since: now
});

/** The time the photo has left on screen. */
export function left(clock: Clock, now: number): number {
	const shown = clock.shown + (clock.since === null ? 0 : now - clock.since);
	return Math.max(0, PHOTO_MS - shown);
}

export function pause(clock: Clock, now: number): Clock {
	if (clock.since === null) return clock;
	return { ...clock, shown: clock.shown + now - clock.since, since: null };
}

export function resume(clock: Clock, now: number): Clock {
	return clock.since === null ? { ...clock, since: now } : clock;
}

/**
 * One photo on (1) or back (-1), shown from its start, still paused if it was. Null: next
 * after the last photo, the story is over. Back from the first starts it again.
 */
export function step(clock: Clock, by: 1 | -1, now: number): Clock | null {
	const index = Math.max(0, clock.index + by);
	if (index >= clock.count) return null;
	return { ...clock, index, shown: 0, since: clock.since === null ? null : now };
}
