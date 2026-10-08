import { describe, expect, it } from 'vitest';
import { suggester } from './suggest';

describe('suggester', () => {
	it('fills an empty field and follows the choice as it changes', () => {
		const suggest = suggester();
		expect(suggest('', 'Photos')).toBe('Photos');
		expect(suggest('Photos', '2019')).toBe('2019');
		expect(suggest('2019', '')).toBe('');
	});

	it('leaves a name the user typed alone, whatever is chosen next', () => {
		const suggest = suggester();
		suggest('', 'Photos');
		expect(suggest('Holidays', '2019')).toBe('Holidays');
		expect(suggest('Holidays', 'Trips')).toBe('Holidays');
	});

	it('follows again once the field is back to what was suggested last', () => {
		const suggest = suggester();
		suggest('', 'Photos');
		suggest('Holidays', '2019');
		expect(suggest('2019', 'Trips')).toBe('Trips');
	});

	it('does not take a typed name for its own before anything was suggested', () => {
		expect(suggester()('Holidays', 'Photos')).toBe('Holidays');
	});

	it('keeps each field apart', () => {
		const one = suggester();
		const other = suggester();
		one('', 'Photos');
		expect(other('Photos', '2019')).toBe('Photos');
	});
});
