import type { AssetSummary } from './api';

export type MonthGroup = { key: string; label: string; items: AssetSummary[] };

const MONTH = new Intl.DateTimeFormat('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' });

/** Group assets (already newest first) into calendar months, keeping order. */
export function groupByMonth(assets: AssetSummary[]): MonthGroup[] {
	const groups: MonthGroup[] = [];
	for (const asset of assets) {
		const key = asset.taken_at.slice(0, 7); // YYYY-MM of the local wall-clock time
		let group = groups.at(-1);
		if (!group || group.key !== key) {
			const [year, month] = key.split('-').map(Number);
			group = { key, label: MONTH.format(Date.UTC(year, month - 1, 1)), items: [] };
			groups.push(group);
		}
		group.items.push(asset);
	}
	return groups;
}

/** Width ÷ height, falling back to 3:2 when the size is unknown. Clamped so panoramas stay sane. */
export function aspect(asset: Pick<AssetSummary, 'width' | 'height'>): number {
	if (!asset.width || !asset.height) return 1.5;
	return Math.min(Math.max(asset.width / asset.height, 0.4), 4);
}
