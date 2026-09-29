import { describe, expect, it } from 'vitest';
import { streamAssets, type AssetPage } from './api';

const page = (ids: number[], next: string | null): AssetPage => ({
	items: ids.map((id) => ({
		id,
		taken_at: '2020-01-01T00:00:00',
		tz_offset_minutes: null,
		date_source: 'exif',
		width: 4,
		height: 3,
		kind: 'photo',
		thumb: null,
		preview_ready: false
	})),
	next_cursor: next
});

describe('streamAssets', () => {
	it('hands over each page as it arrives and follows cursors to the end', async () => {
		const urls: string[] = [];
		const responses = [page([1, 2], 'c1'), page([3], null)];
		const fakeFetch = (async (url: string) => {
			urls.push(url);
			return new Response(JSON.stringify(responses.shift()));
		}) as typeof fetch;
		const seen: number[][] = [];
		await streamAssets((items) => seen.push(items.map((a) => a.id)), fakeFetch, 2);
		expect(seen).toEqual([[1, 2], [3]]);
		expect(urls).toEqual(['/api/assets?limit=2', '/api/assets?limit=2&cursor=c1']);
	});

	it('stops with an error when the server fails', async () => {
		const failing = (async () => new Response('no', { status: 500 })) as typeof fetch;
		await expect(streamAssets(() => {}, failing)).rejects.toThrow('500');
	});
});
