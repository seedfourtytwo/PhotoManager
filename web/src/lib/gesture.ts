/**
 * What a touch on the open photo means (spec §4.3, §6): one pure recogniser, so the thresholds
 * are tested without a screen. Every gesture also has a button that does the same thing.
 * A double tap zooms (lib/zoom.ts, which also has what two fingers do).
 */
export type Point = { x: number; y: number; t: number };
/** The way a drag goes, chosen once it leaves the slop and kept until the finger lifts. */
export type Axis = 'x' | 'y';
export type Gesture = 'tap' | 'double-tap' | 'previous' | 'next' | 'details' | 'close';

/** A finger that moved no further than this has not moved. Shared with the grid's long press (press.ts). */
export const SLOP = 10;
const TAP_MS = 500;
/** A second tap this soon, and this close to the first, makes a double tap. */
export const DOUBLE_TAP_MS = 300;
const DOUBLE_TAP_REACH = 30;
/** Past this share of the width, a sideways drag turns to the next photo when let go. */
const TURN_SHARE = 0.35;
/** A flick this fast (px/ms) turns, however short it was. */
const FLICK = 0.4;
/** The finger's speed is read over its last this many milliseconds. */
const VELOCITY_MS = 80;
/** Faster than a thumb goes (px/ms): what is read faster is two samples too close together. */
const MAX_SPEED = 4;
/** Past the first or the last photo, the photo moves this much of the pull: it resists. */
const RESIST = 1 / 3;
const DETAILS = 60;
const CLOSE = 80;

/** The axis a drag goes along: none inside the slop, then the longer one. */
export function lockAxis(down: Point, now: Point): Axis | null {
	const dx = now.x - down.x;
	const dy = now.y - down.y;
	if (Math.hypot(dx, dy) <= SLOP) return null;
	return Math.abs(dx) > Math.abs(dy) ? 'x' : 'y';
}

/**
 * What a press that ended means; null for a press that means nothing. Swipes are touch only.
 * A sideways drag is the track's to settle (`turn`); `axis` is the one the drag locked to.
 */
export function recognise(
	down: Point,
	up: Point,
	lastTap: Point | null,
	touch: boolean,
	axis: Axis | null = lockAxis(down, up)
): Gesture | null {
	const dy = up.y - down.y;
	if (axis === null) {
		if (up.t - down.t >= TAP_MS) return null;
		const again =
			lastTap !== null &&
			up.t - lastTap.t < DOUBLE_TAP_MS &&
			Math.hypot(up.x - lastTap.x, up.y - lastTap.y) < DOUBLE_TAP_REACH;
		return again ? 'double-tap' : 'tap';
	}
	if (!touch || axis === 'x') return null;
	if (dy < -DETAILS) return 'details';
	return dy > CLOSE ? 'close' : null;
}

/**
 * How far the photo is pulled while the finger is down, along the drag's axis only: sideways
 * it follows x however the finger drifts; downwards it follows y, and never upwards (swiping
 * up brings the details in; the photo stays).
 */
export function pull(down: Point, now: Point, axis: Axis): { x: number; y: number } {
	if (axis === 'x') return { x: now.x - down.x, y: 0 };
	return { x: 0, y: Math.max(0, now.y - down.y) };
}

/** Which neighbours the open photo has. */
export type Ends = { previous: boolean; next: boolean };

/** A sideways pull as the photo follows it: resisting where there is no photo to pull in. */
export function edge(dx: number, ends: Ends): number {
	const open = dx > 0 ? ends.previous : ends.next;
	return open ? dx : dx * RESIST;
}

/** The finger's speed along x, in px/ms, over its last 80 ms or so; 0 when that says nothing. */
export function velocity(samples: Point[]): number {
	const last = samples.at(-1);
	if (!last) return 0;
	// From the newest sample that is old enough; a finger that sent few moves lately is read
	// from further back rather than from none.
	const first = samples.findLast((p) => last.t - p.t >= VELOCITY_MS) ?? samples[0];
	const dt = last.t - first.t;
	if (dt <= 0) return 0;
	const speed = (last.x - first.x) / dt;
	return Math.max(-MAX_SPEED, Math.min(MAX_SPEED, speed));
}

/**
 * Where a sideways drag let go goes: 1 to the next photo, -1 to the previous, 0 back. Far
 * enough, or flicked that way, turns; a flick back against the drag cancels it.
 */
export function turn(dx: number, vx: number, width: number, ends: Ends): -1 | 0 | 1 {
	if (dx === 0) return 0;
	const way = dx < 0 ? 1 : -1;
	const goes =
		Math.abs(vx) > FLICK ? Math.sign(vx) === Math.sign(dx) : Math.abs(dx) > width * TURN_SHARE;
	if (!goes) return 0;
	return (way === 1 ? ends.next : ends.previous) ? way : 0;
}

/**
 * The photo track on its way: where it is from the open photo (px), how fast (px/ms), and the
 * turn it makes when it arrives (0: back home).
 */
export type Slide = { x: number; v: number; by: -1 | 0 | 1 };

/**
 * A step asked for (an arrow key, an edge button) while the track still slides. The same way
 * as it goes, the turn on its way is made now: its photo becomes the open one, the track is put
 * a photo back under it (nothing on screen moves), and it goes on to the next one at the speed
 * it had. The other way, it goes back home and no turn is made. It never runs more than a photo
 * behind: steps asked faster than that skip the photos in between, and it slides on from rest.
 */
export function restep(
	slide: Slide,
	step: -1 | 1,
	width: number
): { made: -1 | 0 | 1; slide: Slide } {
	const { x, v, by } = slide;
	if (by === -step) return { made: 0, slide: { x, v, by: 0 } };
	if (by === 0) return { made: 0, slide: { x, v, by: step } };
	const behind = x + by * width;
	if (Math.abs(behind) < width) return { made: by, slide: { x: behind, v, by } };
	return { made: by, slide: { x: by * width, v: 0, by } };
}
