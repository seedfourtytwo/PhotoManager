/**
 * What a touch on the open photo means (spec §4.3, §6): one pure recogniser, so the thresholds
 * are tested without a screen. Every gesture also has a button that does the same thing.
 */
export type Point = { x: number; y: number; t: number };
export type Gesture = 'tap' | 'double-tap' | 'previous' | 'next' | 'details' | 'close';

/** A finger that moved no further than this has not moved. Shared with the grid's long press (press.ts). */
export const SLOP = 10;
const TAP_MS = 500;
/** A second tap this soon, and this close to the first, makes a double tap. */
export const DOUBLE_TAP_MS = 300;
const DOUBLE_TAP_REACH = 30;
const STEP = 50;
const DETAILS = 60;
const CLOSE = 80;

/** What a press that ended means; null for a press that means nothing. Swipes are touch only. */
export function recognise(
	down: Point,
	up: Point,
	lastTap: Point | null,
	touch: boolean
): Gesture | null {
	const dx = up.x - down.x;
	const dy = up.y - down.y;
	if (Math.hypot(dx, dy) <= SLOP) {
		if (up.t - down.t >= TAP_MS) return null;
		const again =
			lastTap !== null &&
			up.t - lastTap.t < DOUBLE_TAP_MS &&
			Math.hypot(up.x - lastTap.x, up.y - lastTap.y) < DOUBLE_TAP_REACH;
		return again ? 'double-tap' : 'tap';
	}
	if (!touch) return null;
	if (Math.abs(dx) > Math.abs(dy)) {
		if (Math.abs(dx) <= STEP) return null;
		return dx < 0 ? 'next' : 'previous';
	}
	if (dy < -DETAILS) return 'details';
	return dy > CLOSE ? 'close' : null;
}

/**
 * How far the photo is pulled while the finger is down: along the longer axis only, and never
 * upwards (swiping up brings the details in; the photo stays).
 */
export function pull(down: Point, now: Point): { x: number; y: number } {
	const dx = now.x - down.x;
	const dy = now.y - down.y;
	if (Math.hypot(dx, dy) <= SLOP) return { x: 0, y: 0 };
	if (Math.abs(dx) > Math.abs(dy)) return { x: dx, y: 0 };
	return { x: 0, y: Math.max(0, dy) };
}
