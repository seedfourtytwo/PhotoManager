/**
 * How Home's rows of cards are sized (spec flight/home §2–7): a rail shows `n.3` cards so the
 * next one always peeks past the screen's edge; Pinned and New this week are strips of photos at
 * their true shape and one height, so neither ends in a ragged row.
 */
import type { HomeSection } from './api/types';

/** Cards on screen at once, on a laptop and on a phone. */
export const RAILS = {
	/** Rediscover's other photos, under its hero. */
	dozen: { wide: 4.3, phone: 2.3 },
	memories: { wide: 3.3, phone: 1.3 },
	years: { wide: 5.3, phone: 2.3 }
} as const;

/** Pinned photos Home shows; See all opens the rest in the Library. */
export const PINNED_SHOWN = 24;

export const railGap = (phone: boolean) => (phone ? 12 : 16);
/** Between the photos of a strip. */
export const STRIP_GAP = 4;

/** A card's width when `visible` of them share `width` with a gap after each whole one. */
export function cardWidth(width: number, visible: number, gap: number): number {
	return Math.max(0, (width - Math.floor(visible) * gap) / visible);
}

export const stripHeight = (phone: boolean) => (phone ? 160 : 220);

/** A photo's width in a strip: its shape at the strip's height (square while not known). */
export function stripWidth(aspect: number, height: number): number {
	return Math.round((aspect > 0 ? aspect : 1) * height);
}

/** A trailing See all card: some shown, and more where they came from. */
export const seeAll = (shown: number, more: boolean) => shown > 0 && more;

/** The block whose hero leads Home, full-bleed under the bars: the first, if it is a hero. */
export function leadOf(blocks: readonly HomeSection[]): 'on_this_day' | 'rediscover' | null {
	const [first] = blocks;
	return first === 'on_this_day' || first === 'rediscover' ? first : null;
}
