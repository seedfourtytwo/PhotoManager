import { describe, expect, it } from 'vitest';
import type { AssetSummary } from './api';
import { aspect, groupByMonth } from './timeline';

const asset = (id: number, taken_at: string, width = 4, height = 3): AssetSummary => ({
	id,
	taken_at,
	tz_offset_minutes: null,
	date_source: 'exif',
	width,
	height,
	kind: 'photo',
	thumb: { url: `/api/assets/${id}/thumb` },
	preview_ready: true
});

describe('groupByMonth', () => {
	it('groups consecutive photos by local month and keeps order', () => {
		const groups = groupByMonth([
			asset(1, '2019-07-31T23:59:00'),
			asset(2, '2019-07-01T00:00:00'),
			asset(3, '2019-06-30T12:00:00')
		]);
		expect(groups.map((g) => [g.label, g.items.map((a) => a.id)])).toEqual([
			['July 2019', [1, 2]],
			['June 2019', [3]]
		]);
	});

	it('returns nothing for an empty library', () => {
		expect(groupByMonth([])).toEqual([]);
	});
});

describe('aspect', () => {
	it('uses true proportions', () => {
		expect(aspect({ width: 3000, height: 4000 })).toBe(0.75);
	});
	it('falls back to 3:2 and clamps extremes', () => {
		expect(aspect({ width: null, height: 100 })).toBe(1.5);
		expect(aspect({ width: 10000, height: 100 })).toBe(4);
		expect(aspect({ width: 10, height: 1000 })).toBe(0.4);
	});
});
