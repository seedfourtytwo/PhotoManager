/**
 * Zoom levels of the photo grids (spec library-search-viewer §1, Grid): five row heights per
 * device, stepped by a pinch, by ⌘/Ctrl with + and −, or by a trackpad pinch (a wheel with
 * Ctrl); the level is remembered per device. Pure, so the thresholds are tested without a
 * screen; lib/state/grid-zoom.svelte.ts holds the level and the grids read it.
 */
import type { ThumbSize } from './look';

/** Row heights (px), smallest first. 60 on a phone is the "years" density, nine across. */
export const LEVELS = {
	phone: [60, 84, 110, 160, 240],
	laptop: [120, 160, 220, 300, 420]
} as const;
export type Device = keyof typeof LEVELS;

/** Two fingers this much further apart (or closer) than where they started: one level. */
export const PINCH_IN = 1.15;
export const PINCH_OUT = 0.87;
/** A trackpad pinch: this much wheel (px) with Ctrl is one level. */
const WHEEL_STEP = 40;
const STORAGE_KEY = 'grid-zoom';
const TOP = LEVELS.phone.length - 1;

/** A phone is narrower than 640 px (as `rowHeightFor`); a tablet zooms as a laptop. */
export const deviceOf = (width: number): Device => (width < 640 ? 'phone' : 'laptop');

/** Where a device starts before it has been zoomed: the look's photo size. */
export function defaultLevel(size: ThumbSize): number {
	return { small: 1, medium: 2, large: 3 }[size];
}

export function rowHeightAt(device: Device, level: number): number {
	return LEVELS[device][Math.min(Math.max(Math.round(level), 0), TOP)];
}

/** One level bigger (+1) or smaller (−1), held at the ends. */
export function stepLevel(level: number, by: 1 | -1): number {
	return Math.min(Math.max(level + by, 0), TOP);
}

/** The step two fingers ask for: their distance now over their distance at the start. */
export function pinchStep(ratio: number): -1 | 0 | 1 {
	if (ratio > PINCH_IN) return 1;
	if (ratio < PINCH_OUT) return -1;
	return 0;
}

/** ⌘/Ctrl with + (or =, the same key unshifted) zooms in, with − out. */
export function keyStep(event: { key: string; metaKey: boolean; ctrlKey: boolean }): -1 | 0 | 1 {
	if (!event.metaKey && !event.ctrlKey) return 0;
	if (event.key === '+' || event.key === '=') return 1;
	if (event.key === '-') return -1;
	return 0;
}

/**
 * A trackpad pinch comes as wheel events with Ctrl: they add up (`sum`) until they reach a
 * step, then count again from nothing. A plain wheel scrolls: it resets the count.
 */
export function wheelStep(
	sum: number,
	event: { ctrlKey: boolean; deltaY: number }
): { step: -1 | 0 | 1; sum: number } {
	if (!event.ctrlKey) return { step: 0, sum: 0 };
	const next = sum + event.deltaY;
	if (next <= -WHEEL_STEP) return { step: 1, sum: 0 };
	if (next >= WHEEL_STEP) return { step: -1, sum: 0 };
	return { step: 0, sum: next };
}

/**
 * Two fingers on the grid: how far apart they are against where the last step was taken.
 * `move` answers the step they ask for and the point between them (where the zoom anchors);
 * null while there are not two fingers down.
 */
export class Pinch {
	#points = new Map<number, { x: number; y: number }>();
	#from: number | null = null;

	get active(): boolean {
		return this.#from !== null;
	}

	down(id: number, x: number, y: number) {
		if (this.#points.size >= 2) return;
		this.#points.set(id, { x, y });
		if (this.#points.size === 2) this.#from = this.#distance();
	}

	move(id: number, x: number, y: number): { step: -1 | 0 | 1; x: number; y: number } | null {
		if (!this.#points.has(id)) return null;
		this.#points.set(id, { x, y });
		if (this.#from === null) return null;
		const now = this.#distance();
		const step = this.#from > 0 ? pinchStep(now / this.#from) : 0;
		if (step) this.#from = now;
		const [a, b] = [...this.#points.values()];
		return { step, x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
	}

	up(id: number) {
		this.#points.delete(id);
		this.#from = null;
	}

	#distance(): number {
		const [a, b] = [...this.#points.values()];
		return Math.hypot(a.x - b.x, a.y - b.y);
	}
}

type Store = Pick<Storage, 'getItem' | 'setItem'>;

function read(storage: Store): Partial<Record<Device, unknown>> {
	try {
		const saved: unknown = JSON.parse(storage.getItem(STORAGE_KEY) ?? '{}');
		return saved && typeof saved === 'object' ? saved : {};
	} catch {
		return {}; // blocked storage or a value written by something else: start afresh
	}
}

/** The level this device was left at, or null when it has none (or none that makes sense). */
export function loadLevel(storage: Store, device: Device): number | null {
	const level = read(storage)[device];
	return Number.isInteger(level) && (level as number) >= 0 && (level as number) <= TOP
		? (level as number)
		: null;
}

export function saveLevel(storage: Store, device: Device, level: number): void {
	try {
		storage.setItem(STORAGE_KEY, JSON.stringify({ ...read(storage), [device]: level }));
	} catch {
		// Private browsing or full storage: the level holds for this visit only.
	}
}
