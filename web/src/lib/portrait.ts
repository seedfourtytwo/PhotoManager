/**
 * Portrait geometry. A portrait is a circle on a photo as displayed, without its edits: the
 * centre as fractions of the width and height, and `size`, the side of the square round it
 * as a fraction of the photo's shorter edge (1 = the largest circle the photo holds). The
 * server cuts the picture (`domain/faces.py` holds the same rules); this is the dialog's
 * side of it: a square stage shows exactly that square, under a round window.
 *
 * `aspect` is the photo's width / height. Stage positions and distances are fractions of the
 * stage (0.5, 0.5 is its middle).
 */
export type Circle = { cx: number; cy: number; size: number };

/** The closest cut: 1/50 of the shorter edge, as on the server. */
export const MIN_SIZE = 0.02;
/** One press of an arrow key moves by this share of what the window shows. */
const KEY_PAN = 0.05;
/** One press of + or - zooms by this factor. */
const KEY_ZOOM = 1.1;
/** Per pixel the wheel reports: a mouse's notch (100) is about a fifth, a trackpad glides. */
const WHEEL_ZOOM = 0.002;

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);

/** How many shorter edges the photo is wide and high (one of the two is 1). */
function edges(aspect: number): { wide: number; high: number } {
	return { wide: Math.max(aspect, 1), high: Math.max(1 / aspect, 1) };
}

/** The nearest circle that lies inside the photo and is not a speck. */
export function fitCircle(circle: Circle, aspect: number): Circle {
	const { wide, high } = edges(aspect);
	const size = clamp(circle.size, MIN_SIZE, 1);
	const halfW = size / wide / 2;
	const halfH = size / high / 2;
	return {
		cx: clamp(circle.cx, halfW, 1 - halfW),
		cy: clamp(circle.cy, halfH, 1 - halfH),
		size
	};
}

/** Where the photo sits so that the circle fills the stage: percentages of the stage. */
export function photoLayout(
	circle: Circle,
	aspect: number
): { left: number; top: number; width: number; height: number } {
	const { wide, high } = edges(aspect);
	const width = (wide / circle.size) * 100;
	const height = (high / circle.size) * 100;
	return { width, height, left: 50 - circle.cx * width, top: 50 - circle.cy * height };
}

/** Drag the photo by (dx, dy) of the stage: it follows the hand, so the centre goes the other way. */
export function pan(circle: Circle, dx: number, dy: number, aspect: number): Circle {
	const { wide, high } = edges(aspect);
	return fitCircle(
		{
			...circle,
			cx: circle.cx - (dx * circle.size) / wide,
			cy: circle.cy - (dy * circle.size) / high
		},
		aspect
	);
}

/** Zoom in (`factor` > 1) or out, keeping what is under the stage point (x, y) where it is. */
export function zoomAbout(
	circle: Circle,
	factor: number,
	x: number,
	y: number,
	aspect: number
): Circle {
	if (!Number.isFinite(factor) || factor <= 0) return circle;
	const { wide, high } = edges(aspect);
	const size = clamp(circle.size / factor, MIN_SIZE, 1);
	const shift = circle.size - size;
	return fitCircle(
		{
			cx: circle.cx + ((x - 0.5) * shift) / wide,
			cy: circle.cy + ((y - 0.5) * shift) / high,
			size
		},
		aspect
	);
}

/** The zoom factor for a turn of the wheel: away from you (negative) zooms in. */
export function wheelZoom(deltaY: number): number {
	return Math.exp(-deltaY * WHEEL_ZOOM);
}

/** What a key does on the stage: arrows move the circle over the photo, + and - zoom. */
export function nudge(circle: Circle, key: string, aspect: number): Circle | null {
	const moves: Record<string, [number, number]> = {
		ArrowLeft: [KEY_PAN, 0],
		ArrowRight: [-KEY_PAN, 0],
		ArrowUp: [0, KEY_PAN],
		ArrowDown: [0, -KEY_PAN]
	};
	const move = moves[key];
	if (move) return pan(circle, move[0], move[1], aspect);
	if (key === '+' || key === '=') return zoomAbout(circle, KEY_ZOOM, 0.5, 0.5, aspect);
	if (key === '-') return zoomAbout(circle, 1 / KEY_ZOOM, 0.5, 0.5, aspect);
	return null;
}
