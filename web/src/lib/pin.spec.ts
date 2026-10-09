import { describe, expect, it } from 'vitest';
import { PAD_KEYS, pressKey } from './pin';

describe('number pad', () => {
	it('lays its keys out as a phone does: 1 to 9, then 0 with Delete to its right', () => {
		expect(PAD_KEYS).toEqual(['1', '2', '3', '4', '5', '6', '7', '8', '9', null, '0', 'delete']);
	});
	it('a digit joins the end', () => {
		expect(pressKey('', '1')).toBe('1');
		expect(pressKey('12', '0')).toBe('120');
	});
	it('a fifth digit is not taken: a PIN has four', () => {
		expect(pressKey('1234', '5')).toBe('1234');
	});
	it('Delete takes the last digit back, and nothing from nothing', () => {
		expect(pressKey('123', 'delete')).toBe('12');
		expect(pressKey('', 'delete')).toBe('');
	});
});
