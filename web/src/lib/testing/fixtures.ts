import type { AssetOut } from '../api/types';

/** A minimal list item for tests; override what the test is about. */
export const makeAsset = (
	id: number,
	taken_at = '2020-01-01T12:00:00',
	width = 4,
	height = 3,
	extra: Partial<AssetOut> = {}
): AssetOut => ({
	id,
	taken_at,
	tz_offset_minutes: null,
	date_source: 'exif',
	width,
	height,
	kind: 'photo',
	thumb: { url: `/api/assets/${id}/thumb` },
	preview_ready: true,
	favourite: false,
	pinned: false,
	hidden: false,
	private: false,
	place: null,
	edited: false,
	variant_of: null,
	group_id: null,
	...extra
});
