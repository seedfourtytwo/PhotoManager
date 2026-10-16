import { describe, expect, it } from 'vitest';
import {
	DEFAULT_OPTIONS,
	EDGE_PRESETS,
	applySimple,
	buildDownloadRequest,
	frameError,
	isUntouched,
	scopeLabel,
	simpleChoices,
	simpleOf
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
			naming: 'name',
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
});

describe('the plain choices the dialog opens on', () => {
	it('are full size or smaller; a with-edits choice comes only when there are edits', () => {
		expect(simpleChoices(false).map((c) => c.value)).toEqual(['full', 'small']);
		expect(simpleChoices(true).map((c) => c.value)).toEqual(['full', 'edited', 'small']);
	});

	it('say in words whether the edits come along', () => {
		const about = (edited: boolean) =>
			Object.fromEntries(simpleChoices(edited).map((c) => [c.value, c.about]));
		expect(about(false).full).not.toMatch(/edit/);
		expect(about(false).small).not.toMatch(/edit/);
		expect(about(true).full).toMatch(/without the edits/);
		expect(about(true).small).toMatch(/Edits included/);
	});

	it('the default is full size: the file as it was taken', () => {
		expect(simpleOf(DEFAULT_OPTIONS, false)).toBe('full');
		expect(isUntouched(applySimple({ ...DEFAULT_OPTIONS, max_edge: 1080 }, 'full'))).toBe(true);
	});

	it('smaller is a 2048 JPEG, with edits a full-size one', () => {
		expect(applySimple(DEFAULT_OPTIONS, 'small')).toMatchObject({ format: 'jpeg', max_edge: 2048 });
		expect(applySimple(DEFAULT_OPTIONS, 'edited')).toMatchObject({
			format: 'jpeg',
			max_edge: null
		});
		expect(simpleOf(applySimple(DEFAULT_OPTIONS, 'small'), true)).toBe('small');
		expect(simpleOf(applySimple(DEFAULT_OPTIONS, 'edited'), true)).toBe('edited');
	});

	it('a choice changes format and size only', () => {
		const mine = {
			...DEFAULT_OPTIONS,
			strip_location: true,
			naming: 'date',
			folders: 'year'
		} as const;
		expect(applySimple(mine, 'small')).toEqual({ ...mine, format: 'jpeg', max_edge: 2048 });
		expect(simpleOf({ ...mine, quality: 40 }, false)).toBe('full');
	});

	// "More options" never leaves the plain choices with none chosen: they are sizes, so
	// whatever is set by hand is still one of them.
	it('what is set by hand still reads as a plain choice, by its size', () => {
		expect(simpleOf({ ...DEFAULT_OPTIONS, format: 'png' }, false)).toBe('full');
		expect(simpleOf({ ...DEFAULT_OPTIONS, format: 'jpeg' }, false)).toBe('full');
		expect(simpleOf({ ...DEFAULT_OPTIONS, max_edge: 2048 }, false)).toBe('small');
		expect(simpleOf({ ...DEFAULT_OPTIONS, format: 'jpeg', max_edge: 1280 }, false)).toBe('small');
		expect(simpleOf({ ...DEFAULT_OPTIONS, format: 'webp', max_edge: 3840 }, true)).toBe('small');
	});

	it('with edits, a full-size made file is “With edits” and the original is “Full size”', () => {
		expect(simpleOf({ ...DEFAULT_OPTIONS, format: 'png' }, true)).toBe('edited');
		expect(simpleOf(DEFAULT_OPTIONS, true)).toBe('full');
	});

	it('the plain choice it reads as is always one that is offered', () => {
		for (const edited of [false, true])
			for (const format of ['original', 'jpeg', 'png', 'webp'] as const)
				for (const max_edge of [null, 3840, 1080]) {
					const offered = simpleChoices(edited).map((c) => c.value);
					expect(offered).toContain(simpleOf({ ...DEFAULT_OPTIONS, format, max_edge }, edited));
				}
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
