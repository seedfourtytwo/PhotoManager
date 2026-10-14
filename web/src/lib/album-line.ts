/** What an album's page says under its title: how many photos, and when they are from. */
import type { AssetOut } from './api/types';
import { photos } from './format';

const MONTH = new Intl.DateTimeFormat('en-GB', { month: 'long', timeZone: 'UTC' });
const monthName = (yyyyMm: string) => MONTH.format(Date.UTC(2000, Number(yyyyMm.slice(5, 7)) - 1));

/**
 * "12 photos, July 2024", "2 photos, June to August 2024", "3 photos, 2019 to 2024". The
 * photos may be in any order (an album is arranged by hand); dates are the wall-clock day.
 */
export function albumLine(items: readonly Pick<AssetOut, 'taken_at'>[]): string {
	if (items.length === 0) return photos(0);
	const months = items.map((a) => a.taken_at.slice(0, 7)).sort();
	const [first, last] = [months[0], months.at(-1)!];
	const [firstYear, lastYear] = [first.slice(0, 4), last.slice(0, 4)];
	let span: string;
	if (first === last) span = `${monthName(first)} ${firstYear}`;
	else if (firstYear === lastYear) span = `${monthName(first)} to ${monthName(last)} ${lastYear}`;
	else span = `${firstYear} to ${lastYear}`;
	return `${photos(items.length)}, ${span}`;
}
