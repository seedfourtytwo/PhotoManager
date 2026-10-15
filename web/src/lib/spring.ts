/**
 * Springs: what carries a gesture to rest (DESIGN_PRINCIPLES §1.9). A spring starts at the
 * finger's own speed, so a flick carries on as thrown. The photo track uses the critically
 * damped `paging` spring (no bounce past the next photo, spec §4.3); sheets and the CSS curve
 * `--ease-spring` use `gentle`, a touch underdamped like iOS. Positions are in px, speeds in
 * px/ms. `step` is pure, so the motion is tested without a screen.
 */
export type Motion = { x: number; v: number };
/** Stiffness and damping per unit mass, in s⁻² and s⁻¹. */
export type SpringConfig = { stiffness: number; damping: number };

/** The photo track: arrives in about its 300 ms period without overshooting. */
const PAGING_OMEGA = (2 * Math.PI) / 0.3;
export const SPRINGS = {
	paging: { stiffness: PAGING_OMEGA ** 2, damping: 2 * PAGING_OMEGA },
	gentle: { stiffness: 300, damping: 30 }
} satisfies Record<string, SpringConfig>;

/** Integration steps no longer than this (ms): the same motion at 60 and 120 Hz, and a long
 *  frame cannot blow the spring up. */
const MAX_DT = 4;
/** Closer than this (px) and slower than that (px/ms), the eye sees it still. */
const REST_X = 0.5;
const REST_V = 0.02;

/** Where the spring is `dt` ms later, pulling `from` towards `to`. */
export function step(from: Motion, to: number, dt: number, spring = SPRINGS.paging): Motion {
	let x = from.x;
	let v = from.v * 1000; // px/s, to match the constants
	for (let left = dt; left > 0; left -= MAX_DT) {
		const h = Math.min(MAX_DT, left) / 1000;
		v += (-spring.stiffness * (x - to) - spring.damping * v) * h;
		x += v * h;
	}
	return { x, v: v / 1000 };
}

export function atRest(motion: Motion, to: number): boolean {
	return Math.abs(motion.x - to) < REST_X && Math.abs(motion.v) < REST_V;
}

type Animation = {
	from: number;
	to: number;
	/** The finger's speed at release, px/ms. */
	velocity: number;
	config?: SpringConfig;
	onFrame: (x: number) => void;
	onRest?: () => void;
	reduced?: boolean;
	frame?: (callback: (t: number) => void) => number;
	cancel?: (handle: number) => void;
};

/** Runs a spring a frame at a time through `onFrame` (the caller writes a transform). Under
 *  reduced motion it lands at once. `stop()` leaves it where it is and returns that place. */
export function animate({
	from,
	to,
	velocity,
	config = SPRINGS.gentle,
	onFrame,
	onRest,
	reduced = globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false,
	frame = requestAnimationFrame,
	cancel = cancelAnimationFrame
}: Animation): { stop(): number } {
	let motion: Motion = { x: from, v: velocity };
	let last: number | null = null;
	let handle = 0;
	const tick = (t: number) => {
		motion = step(motion, to, last === null ? 0 : t - last, config);
		last = t;
		if (atRest(motion, to)) {
			motion = { x: to, v: 0 };
			handle = 0;
			onFrame(to);
			onRest?.();
		} else {
			onFrame(motion.x);
			handle = frame(tick);
		}
	};
	if (reduced) {
		motion = { x: to, v: 0 };
		onFrame(to);
		onRest?.();
	} else handle = frame(tick);
	return {
		stop() {
			if (handle) cancel(handle);
			handle = 0;
			return motion.x;
		}
	};
}

/** The spring from 0 to 1 at rest as a CSS `linear()` easing: the shape of `--ease-spring`. */
export function toLinearEasing(config: SpringConfig, samples = 20): string {
	const DISTANCE = 100; // px: rests within half a percent, so the curve has no long tail
	const path: number[] = [];
	for (let at: Motion = { x: 0, v: 0 }; !atRest(at, DISTANCE);) {
		at = step(at, DISTANCE, 1, config);
		path.push(at.x / DISTANCE);
	}
	const points = Array.from({ length: samples - 1 }, (_, i) =>
		i === 0 ? 0 : Math.round(path[Math.floor((i * path.length) / (samples - 1))] * 1000) / 1000
	);
	return `linear(${[...points, 1].join(', ')})`;
}
