/**
 * Zoom in the photo view: how large the open photo is and where it sits. Pure, so the limits
 * are tested without a screen. Lengths are CSS pixels; a spot is measured from the middle of
 * the stage, which is also the middle of the photo at its fit.
 */
export type View = { scale: number; x: number; y: number };
export type Size = { w: number; h: number };
export type Spot = { x: number; y: number };

/** The whole photo in view: where every photo opens. */
export const FIT: View = { scale: 1, x: 0, y: 0 };
/** The preview is 2048 px on its long side: past this a phone shows more blur than detail. */
export const MAX_SCALE = 4;
/** What a double tap zooms in to. */
export const TAP_SCALE = 2.5;
/** How small two fingers may squeeze the photo before it springs back to its fit. */
const PINCH_FLOOR = 0.5;

export const zoomed = (view: View): boolean => view.scale > 1;

const within = (value: number, limit: number) => Math.min(Math.max(value, -limit), limit) + 0;

/** The view with its size held between `floor` and the largest, and no edge pulled into the stage. */
function held(view: View, photo: Size, stage: Size, floor: number): View {
	const scale = Math.min(Math.max(Number.isFinite(view.scale) ? view.scale : 1, floor), MAX_SCALE);
	// A side the photo does not fill has no travel: the photo stays centred on it.
	const travel = (side: number, room: number) => Math.max(0, (side * scale - room) / 2);
	return {
		scale,
		x: within(view.x, travel(photo.w, stage.w)),
		y: within(view.y, travel(photo.h, stage.h))
	};
}

/** Where a photo may rest: never smaller than its fit. */
export function settle(view: View, photo: Size, stage: Size): View {
	return held(view, photo, stage, 1);
}

/** To `scale`, so that what is under `at` stays under it. */
function scaledAt(view: View, at: Spot, scale: number): View {
	const ratio = scale / view.scale;
	return { scale, x: at.x - (at.x - view.x) * ratio, y: at.y - (at.y - view.y) * ratio };
}

export function zoomAt(view: View, at: Spot, scale: number, photo: Size, stage: Size): View {
	const target = Math.min(Math.max(Number.isFinite(scale) ? scale : 1, 1), MAX_SCALE);
	return settle(scaledAt(view, at, target), photo, stage);
}

/** A double tap: in on the spot tapped, or back to the fit from any size. */
export function toggle(view: View, at: Spot, photo: Size, stage: Size): View {
	return zoomed(view) ? FIT : zoomAt(view, at, TAP_SCALE, photo, stage);
}

const between = ([a, b]: [Spot, Spot]): Spot => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
const apart = ([a, b]: [Spot, Spot]) => Math.hypot(a.x - b.x, a.y - b.y);

/**
 * Two fingers: `start` is the view when the second one landed, `from` where both were then,
 * `to` where they are now. The photo grows by how far they spread and follows their middle.
 */
export function pinch(
	start: View,
	from: [Spot, Spot],
	to: [Spot, Spot],
	photo: Size,
	stage: Size
): View {
	const spread = apart(from);
	const scale = spread > 0 ? start.scale * (apart(to) / spread) : start.scale;
	const bounded = Math.min(Math.max(scale, PINCH_FLOOR), MAX_SCALE);
	const was = between(from);
	const now = between(to);
	const grown = scaledAt(start, was, bounded);
	return held(
		{ scale: bounded, x: grown.x + now.x - was.x, y: grown.y + now.y - was.y },
		photo,
		stage,
		PINCH_FLOOR
	);
}

/** One finger moving a zoomed photo by (dx, dy) from where it was when the finger landed. */
export function pan(start: View, dx: number, dy: number, photo: Size, stage: Size): View {
	return settle({ scale: start.scale, x: start.x + dx, y: start.y + dy }, photo, stage);
}
