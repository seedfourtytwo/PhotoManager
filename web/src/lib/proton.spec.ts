import { describe, expect, it } from 'vitest';
import { protonPlaceName } from './proton';

describe('protonPlaceName', () => {
	it('names the Photos section and the top of My files', () => {
		expect(protonPlaceName('/photos')).toBe('Photos');
		expect(protonPlaceName('/my-files')).toBe('My files');
	});
	it('spells out a folder path', () => {
		expect(protonPlaceName('/my-files/Trips/2019 Alps')).toBe('My files / Trips / 2019 Alps');
	});
});
