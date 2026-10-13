import type { AssetOut } from './api/types';
import type { ThumbSize } from './look';

export type MonthGroup = { key: string; label: string; items: AssetOut[] };

const MONTH = new Intl.DateTimeFormat('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' });

export function monthLabel(key: string): string {
	const [year, month] = key.split('-').map(Number);
	return MONTH.format(Date.UTC(year, month - 1, 1));
}

/** Group assets (already newest first) into calendar months, keeping order. */
export function groupByMonth(assets: AssetOut[]): MonthGroup[] {
	const groups: MonthGroup[] = [];
	for (const asset of assets) {
		const key = asset.taken_at.slice(0, 7); // YYYY-MM of the local wall-clock time
		let group = groups.at(-1);
		if (!group || group.key !== key) {
			group = { key, label: monthLabel(key), items: [] };
			groups.push(group);
		}
		group.items.push(asset);
	}
	return groups;
}

/** The narrowest and the widest tile: a strip or a panorama at its own shape would be a sliver. */
const MIN_ASPECT = 0.4;
const MAX_ASPECT = 4;

/** Width ÷ height of the photo's tile, falling back to 3:2 when the size is unknown. */
export function aspect(asset: Pick<AssetOut, 'width' | 'height'>): number {
	if (!asset.width || !asset.height) return 1.5;
	return Math.min(Math.max(asset.width / asset.height, MIN_ASPECT), MAX_ASPECT);
}

/**
 * The tile is not the photo's own shape (a panorama, a tall strip): the photo is shown whole
 * inside it, with room left over, rather than stretched or cropped.
 */
export function letterboxed(asset: Pick<AssetOut, 'width' | 'height'>): boolean {
	if (!asset.width || !asset.height) return false;
	const ratio = asset.width / asset.height;
	return ratio < MIN_ASPECT || ratio > MAX_ASPECT;
}

export type Box = { x: number; y: number; w: number; h: number };
export type Layout = { boxes: Box[]; height: number };

/**
 * Justified rows: every photo keeps its true aspect ratio (never cropped); full rows exactly
 * fill `width`; row heights stay close to `target`. The last row keeps the target height
 * instead of stretching. Greedy, O(n): a row closes when adding the next photo would take it
 * further from the target height than stopping now.
 */
export function justify(aspects: number[], width: number, target: number, gap: number): Layout {
	const boxes: Box[] = [];
	if (width <= 0 || aspects.length === 0) return { boxes, height: 0 };
	let y = 0;
	let start = 0;
	let sum = 0;

	const place = (end: number, height: number) => {
		let x = 0;
		for (let i = start; i < end; i++) {
			const w = aspects[i] * height;
			boxes.push({ x, y, w, h: height });
			x += w + gap;
		}
		y += height + gap;
		start = end;
		sum = 0;
	};

	for (let i = 0; i < aspects.length; i++) {
		const n = i - start + 1;
		const widthAtTarget = (sum + aspects[i]) * target + gap * (n - 1);
		if (widthAtTarget < width) {
			sum += aspects[i];
			continue;
		}
		const withHeight = (width - gap * (n - 1)) / (sum + aspects[i]);
		const withoutHeight = n > 1 ? (width - gap * (n - 2)) / sum : Infinity;
		if (Math.abs(withHeight - target) <= Math.abs(withoutHeight - target)) {
			place(i + 1, withHeight);
		} else {
			place(i, withoutHeight);
			sum = aspects[i];
			if (aspects[i] * target >= width) place(i + 1, width / aspects[i]);
		}
	}
	if (start < aspects.length) place(aspects.length, target);
	return { boxes, height: Math.max(0, y - gap) };
}

/** Target row height for a container width and the look's photo size (DESIGN_PRINCIPLES §3). */
export function rowHeightFor(width: number, size: ThumbSize): number {
	const base = width < 640 ? 110 : 220;
	return Math.round(base * { small: 0.75, medium: 1, large: 1.4 }[size]);
}

/**
 * Indexes [start, end) of the boxes that overlap the vertical band [from, to) (coordinates of
 * the month's grid). Boxes come in rows, top to bottom, so a binary search finds the edges.
 */
export function visibleRange(boxes: readonly Box[], from: number, to: number): [number, number] {
	const first = (pred: (b: Box) => boolean) => {
		let lo = 0;
		let hi = boxes.length;
		while (lo < hi) {
			const mid = (lo + hi) >> 1;
			if (pred(boxes[mid])) hi = mid;
			else lo = mid + 1;
		}
		return lo;
	};
	const start = first((b) => b.y + b.h > from);
	const end = first((b) => b.y >= to);
	return end > start ? [start, end] : [0, 0];
}

export type NavKey = 'ArrowLeft' | 'ArrowRight' | 'ArrowUp' | 'ArrowDown' | 'Home' | 'End';
export const NAV_KEYS: readonly string[] = [
	'ArrowLeft',
	'ArrowRight',
	'ArrowUp',
	'ArrowDown',
	'Home',
	'End'
];

/**
 * The photo an arrow key moves to from `index` in a justified layout: left/right in reading
 * order; up/down to the nearest row above/below, at the photo closest to the same column.
 */
export function neighbour(
	boxes: readonly Pick<Box, 'x' | 'y' | 'w' | 'h'>[],
	index: number,
	key: NavKey
): number | null {
	const n = boxes.length;
	if (key === 'Home') return n ? 0 : null;
	if (key === 'End') return n ? n - 1 : null;
	if (key === 'ArrowLeft') return index > 0 ? index - 1 : null;
	if (key === 'ArrowRight') return index < n - 1 ? index + 1 : null;
	const here = boxes[index];
	const centre = here.x + here.w / 2;
	const down = key === 'ArrowDown';
	// The adjacent row: the nearest y strictly below (or above) this one.
	let rowY: number | null = null;
	for (const b of boxes) {
		const beyond = down ? b.y > here.y + 0.5 : b.y < here.y - 0.5;
		if (beyond && (rowY === null || (down ? b.y < rowY : b.y > rowY))) rowY = b.y;
	}
	if (rowY === null) return null;
	let best: number | null = null;
	let bestDistance = Infinity;
	boxes.forEach((b, i) => {
		if (Math.abs(b.y - rowY!) > 0.5) return;
		const distance = Math.abs(b.x + b.w / 2 - centre);
		if (distance < bestDistance) [best, bestDistance] = [i, distance];
	});
	return best;
}
