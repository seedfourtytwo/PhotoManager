import { describe, expect, it } from 'vitest';
import { CLOSE_DISTANCE, shouldClose } from './sheet-drag';

describe('a sheet pulled down', () => {
	it('closes once pulled far enough, however slowly', () => {
		expect(shouldClose(CLOSE_DISTANCE, 2000)).toBe(true);
		expect(shouldClose(CLOSE_DISTANCE - 1, 2000)).toBe(false);
	});
	it('closes on a short fast flick', () => {
		expect(shouldClose(40, 50)).toBe(true);
	});
	it('stays for a jittery tap, however fast', () => {
		expect(shouldClose(10, 5)).toBe(false);
	});
	it('stays when not pulled at all', () => {
		expect(shouldClose(0, 0)).toBe(false);
	});
});
