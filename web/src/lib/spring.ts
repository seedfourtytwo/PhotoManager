/**
 * A critically damped spring: what carries the photo track to rest after a swipe. It starts
 * at the finger's own speed, so a flick carries on as thrown, and it comes home without
 * bouncing past it (spec §4.3). Pure, so the motion is tested without a screen.
 */
export type Motion = { x: number; v: number };

/** How long the spring takes to (nearly) arrive, in ms: its period. */
const RESPONSE_MS = 300;
const OMEGA = (2 * Math.PI) / RESPONSE_MS;
/** Integration steps no longer than this, so a long frame cannot blow the spring up. */
const MAX_DT = 4;
/** Closer than this (px) and slower than that (px/ms), the eye sees it still. */
const REST_X = 0.5;
const REST_V = 0.02;

/** Where the spring is `dt` ms later, pulling `from` towards `to`. */
export function step(from: Motion, to: number, dt: number): Motion {
	let { x, v } = from;
	for (let left = dt; left > 0; left -= MAX_DT) {
		const h = Math.min(MAX_DT, left);
		v += (-OMEGA * OMEGA * (x - to) - 2 * OMEGA * v) * h;
		x += v * h;
	}
	return { x, v };
}

export function atRest(motion: Motion, to: number): boolean {
	return Math.abs(motion.x - to) < REST_X && Math.abs(motion.v) < REST_V;
}
