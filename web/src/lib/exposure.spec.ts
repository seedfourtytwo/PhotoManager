import { describe, expect, it } from 'vitest';
import { type Exposure, exposureParts, exposureSpoken, shutterText } from './exposure';

const NONE: Exposure = { f_number: null, exposure_time: null, iso: null, focal_length: null };
const ALL: Exposure = { f_number: 2.8, exposure_time: 0.004, iso: 400, focal_length: 35 };
const KEYS = ['f_number', 'exposure_time', 'iso', 'focal_length'] as const;

describe('shutterText', () => {
	it.each([
		[0.004, '1/250 s'],
		[1 / 8000, '1/8000 s'],
		[1 / 60, '1/60 s'],
		[1 / 3, '0.3 s'],
		[0.25, '1/4 s'],
		[0.5, '0.5 s'],
		[1, '1 s'],
		[2.5, '2.5 s'],
		[30, '30 s']
	])('%f seconds reads %s', (seconds, text) => {
		expect(shutterText(seconds)).toBe(text);
	});
});

describe('exposureParts', () => {
	it('all four, in the order a camera shows them', () => {
		expect(exposureParts(ALL)).toEqual(['f/2.8', '1/250 s', 'ISO 400', '35 mm']);
	});

	it('nothing for a photo with no values, and before the details arrive', () => {
		expect(exposureParts(NONE)).toEqual([]);
		expect(exposureParts(null)).toEqual([]);
	});

	it('every combination of missing values leaves out exactly the missing ones', () => {
		const texts = {
			f_number: 'f/2.8',
			exposure_time: '1/250 s',
			iso: 'ISO 400',
			focal_length: '35 mm'
		};
		for (let mask = 0; mask < 1 << KEYS.length; mask++) {
			const kept = KEYS.filter((_, bit) => mask & (1 << bit));
			const some = { ...NONE, ...Object.fromEntries(kept.map((key) => [key, ALL[key]])) };
			expect(exposureParts(some)).toEqual(kept.map((key) => texts[key]));
		}
	});

	it('whole numbers lose their decimals, others keep one', () => {
		expect(exposureParts({ ...NONE, f_number: 11, focal_length: 50 })).toEqual(['f/11', '50 mm']);
		expect(exposureParts({ ...NONE, f_number: 1.8, focal_length: 4.25 })).toEqual([
			'f/1.8',
			'4.3 mm'
		]);
		expect(exposureParts({ ...NONE, f_number: 0.95 })).toEqual(['f/0.95']);
	});

	it('a value no camera writes is left out, not shown as nonsense', () => {
		const broken = { f_number: 0, exposure_time: -1, iso: Number.NaN, focal_length: Infinity };
		expect(exposureParts(broken)).toEqual([]);
	});
});

describe('exposureSpoken', () => {
	it('reads as a person would say it', () => {
		expect(exposureSpoken(ALL)).toEqual(['f 2.8', '1/250 second', 'ISO 400', '35 millimetres']);
	});

	it('counts seconds and millimetres in the singular and the plural', () => {
		expect(exposureSpoken({ ...NONE, exposure_time: 1, focal_length: 1 })).toEqual([
			'1 second',
			'1 millimetre'
		]);
		expect(exposureSpoken({ ...NONE, exposure_time: 2.5 })).toEqual(['2.5 seconds']);
		expect(exposureSpoken({ ...NONE, exposure_time: 0.5 })).toEqual(['0.5 seconds']);
	});

	it('says only what is known', () => {
		expect(exposureSpoken({ ...NONE, iso: 800 })).toEqual(['ISO 800']);
		expect(exposureSpoken(NONE)).toEqual([]);
		expect(exposureSpoken(null)).toEqual([]);
	});
});
