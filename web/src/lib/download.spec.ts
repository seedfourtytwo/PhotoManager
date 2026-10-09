import { describe, expect, it } from 'vitest';
import {
	DEFAULT_OPTIONS,
	EDGE_PRESETS,
	buildDownloadRequest,
	frameError,
	isUntouched,
	scopeLabel,
	singleFileName
} from './download';

describe('download model', () => {
	it('offers the preset long edges from the feature list', () => {
		expect(EDGE_PRESETS.map((p) => p.value)).toEqual([null, 3840, 2048, 1080, 1280]);
	});

	it('builds a contract request with exactly one scope', () => {
		expect(buildDownloadRequest({ ids: [1, 2] }, DEFAULT_OPTIONS)).toEqual({
			ids: [1, 2],
			format: 'original',
			quality: 90,
			max_edge: null,
			strip_location: false,
			strip_all_metadata: false,
			naming: 'original',
			folders: 'flat'
		});
		const byFilter = buildDownloadRequest({ filters: { year: 2019 } }, DEFAULT_OPTIONS);
		expect(Object.keys(byFilter)).not.toContain('ids');
		expect(byFilter).toMatchObject({ filters: { year: 2019 } });
	});

	it('clamps quality and makes “strip all” imply “strip location”', () => {
		const r = buildDownloadRequest(
			{ album_id: 3 },
			{ ...DEFAULT_OPTIONS, quality: 250, strip_all_metadata: true }
		);
		expect(r.quality).toBe(100);
		expect(r.strip_location).toBe(true);
		expect(buildDownloadRequest({ ids: [1] }, { ...DEFAULT_OPTIONS, quality: 0 }).quality).toBe(1);
	});

	it('knows when originals stream untouched', () => {
		expect(isUntouched(DEFAULT_OPTIONS)).toBe(true);
		expect(isUntouched({ ...DEFAULT_OPTIONS, max_edge: 2048 })).toBe(false);
		expect(isUntouched({ ...DEFAULT_OPTIONS, strip_location: true })).toBe(false);
	});

	it('describes the scope in words', () => {
		expect(scopeLabel({ ids: [1] })).toBe('1 selected photo');
		expect(scopeLabel({ ids: [1, 2] })).toBe('2 selected photos');
		expect(scopeLabel({ album_id: 1 })).toBe('this album');
		expect(scopeLabel({ filters: {} }, 40)).toBe('all 40 matching photos');
		expect(scopeLabel({ filters: {} }, 1)).toBe('all 1 matching photo');
		expect(scopeLabel({ filters: {} }, 1204)).toBe('all 1,204 matching photos');
		expect(scopeLabel({ ids: Array.from({ length: 1204 }, (_, i) => i) })).toBe(
			'1,204 selected photos'
		);
	});

	it('names single files by date', () => {
		expect(singleFileName(7, '2019-07-04T18:30:00', 'webp')).toBe('2019-07-04_7.webp');
		expect(singleFileName(7, '2019-07-04T18:30:00', 'original')).toBe('2019-07-04_7.jpg');
	});
});

describe('frameError (what a download frame shows when the server refused)', () => {
	it('is nothing while the file downloads (an empty frame)', () => {
		expect(frameError('')).toBeNull();
		expect(frameError(null)).toBeNull();
	});

	it("reads the server's {detail} sentence", () => {
		expect(frameError('{"detail":"not signed in"}')).toBe('Not signed in');
	});

	it('falls back to a plain sentence for anything else', () => {
		expect(frameError('<h1>502 Bad Gateway</h1>')).toBe(
			'The library server could not make the download.'
		);
	});
});
