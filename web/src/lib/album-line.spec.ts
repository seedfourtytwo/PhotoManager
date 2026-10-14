import { describe, expect, it } from 'vitest';
import { albumLine } from './album-line';

const taken = (...days: string[]) => days.map((day) => ({ taken_at: `${day}T12:00:00` }));

describe('the line under an album’s title', () => {
	it('says how many photos and the month they are from', () => {
		expect(albumLine(taken('2024-07-02', '2024-07-30', '2024-07-14'))).toBe('3 photos, July 2024');
	});
	it('spans the months of one year', () => {
		expect(albumLine(taken('2024-08-01', '2024-06-12'))).toBe('2 photos, June to August 2024');
	});
	it('spans the years', () => {
		expect(albumLine(taken('2019-12-31', '2024-01-01', '2021-05-05'))).toBe(
			'3 photos, 2019 to 2024'
		);
	});
	it('reads the order the album was arranged in, not the dates', () => {
		expect(albumLine(taken('2024-07-30', '2024-06-01'))).toBe('2 photos, June to July 2024');
	});
	it('says the count alone for one photo’s day, and for none', () => {
		expect(albumLine(taken('2024-07-02'))).toBe('1 photo, July 2024');
		expect(albumLine([])).toBe('0 photos');
	});
	it('groups a large count', () => {
		expect(albumLine(taken(...Array(1204).fill('2024-07-02')))).toBe('1,204 photos, July 2024');
	});
});
