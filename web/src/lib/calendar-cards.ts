/**
 * The Library's Years and Months views (spec library-search-viewer §4): a card per year and per
 * month, each with a cover photo. Counts come from /api/calendar; a cover is the first photo of
 * that year or month under the same filters (`/api/assets?…&limit=1`), asked only for the cards
 * that come on screen, until the server has a cover per month of its own (A4).
 */
import type { AssetFilters, AssetOut, AssetPage } from './api/types';
import { MONTHS } from './dates';

export type MonthCard = { key: string; month: number; count: number };
export type YearCard = { year: number; count: number; months: MonthCard[] };

/** Months with photos (YYYY-MM, newest first) as a card per year, newest first. */
export function yearCards(months: readonly { key: string; count: number }[]): YearCard[] {
	const years: YearCard[] = [];
	for (const { key, count } of months) {
		const year = Number(key.slice(0, 4));
		let card = years.at(-1);
		if (!card || card.year !== year) years.push((card = { year, count: 0, months: [] }));
		card.count += count;
		card.months.push({ key, month: Number(key.slice(5, 7)), count });
	}
	return years;
}

/** "July". */
export const monthName = (month: number): string => MONTHS[month - 1];

/** The whole Library, gone to that month (LibraryView reads the `#YYYY-MM`), the filters kept. */
export const monthHref = (query: string, key: string): string => `/${query}#${key}`;

type Fetch = (filters: AssetFilters, cursor: string | null, limit: number) => Promise<AssetPage>;

/** Cover photos, one request per year or month, remembered for the visit. */
export class Covers {
	#fetch: Fetch;
	#known = new Map<string, Promise<AssetOut | null>>();

	constructor(fetch: Fetch) {
		this.#fetch = fetch;
	}

	/** The first photo of the year (or of its month) that the filters show; null if none. */
	of(filters: AssetFilters, year: number, month?: number): Promise<AssetOut | null> {
		const scope: AssetFilters = { ...filters, year, ...(month ? { month } : {}) };
		const key = JSON.stringify(scope);
		let cover = this.#known.get(key);
		if (!cover) {
			cover = this.#fetch(scope, null, 1).then(
				(page) => page.items[0] ?? null,
				() => {
					this.#known.delete(key); // asked again by the next card that shows it
					return null;
				}
			);
			this.#known.set(key, cover);
		}
		return cover;
	}
}
