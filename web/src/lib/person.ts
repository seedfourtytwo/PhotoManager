/** What a person's page says under their name. */
import type { AssetOut } from './api/types';
import type { MonthGroup } from './timeline';
import { photos } from './format';

export type Years = { first: number; last: number };

/**
 * The years of the oldest and the newest photo of a list given newest first; null until the
 * list is whole (`complete`), since an older photo may still be on its way.
 */
export function yearsOf(newestFirst: readonly AssetOut[], complete: boolean): Years | null {
	if (!complete || newestFirst.length === 0) return null;
	const year = (a: AssetOut) => Number(a.taken_at.slice(0, 4));
	return { first: year(newestFirst.at(-1)!), last: year(newestFirst[0]) };
}

/** "27 photos, 2012 to 2026", "3 photos, 2019", or the count alone while the years are not known. */
export function personLine(count: number, years: Years | null): string {
	if (!years) return photos(count);
	const span = years.first === years.last ? `${years.first}` : `${years.first} to ${years.last}`;
	return `${photos(count)}, ${span}`;
}

/**
 * A person's photos as one group: one continuous justified mosaic, so no year ends in a short
 * row (the year in view rides in a chip instead). For Timeline's `grouping`.
 */
export function asOneMosaic(newestFirst: AssetOut[]): MonthGroup[] {
	return newestFirst.length ? [{ key: 'all', label: 'All photos', items: newestFirst }] : [];
}
