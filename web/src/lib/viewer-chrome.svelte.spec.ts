import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ViewerChrome } from './viewer-chrome.svelte';

const MS = 3000;

beforeEach(() => {
	vi.useFakeTimers();
});
afterEach(() => {
	vi.useRealTimers();
});

describe('ViewerChrome', () => {
	it('starts shown and, untouched, stays shown (a phone never hides it by itself)', () => {
		const chrome = new ViewerChrome(MS, () => false);
		vi.advanceTimersByTime(10 * MS);
		expect(chrome.hidden).toBe(false);
	});

	it('a mouse or a key shows it, and it fades after the idle time without either', () => {
		const chrome = new ViewerChrome(MS, () => false);
		chrome.hide();
		chrome.stir();
		expect(chrome.hidden).toBe(false);
		vi.advanceTimersByTime(MS - 1);
		expect(chrome.hidden).toBe(false);
		vi.advanceTimersByTime(1);
		expect(chrome.hidden).toBe(true);
	});

	it('each stir starts the idle wait again', () => {
		const chrome = new ViewerChrome(MS, () => false);
		chrome.stir();
		vi.advanceTimersByTime(MS - 1);
		chrome.stir();
		vi.advanceTimersByTime(MS - 1);
		expect(chrome.hidden).toBe(false);
		vi.advanceTimersByTime(1);
		expect(chrome.hidden).toBe(true);
	});

	it('stays while something on it is in use (an open menu), and fades once it is not', () => {
		let menu = true;
		const chrome = new ViewerChrome(MS, () => menu);
		chrome.stir();
		vi.advanceTimersByTime(3 * MS);
		expect(chrome.hidden).toBe(false);
		menu = false;
		vi.advanceTimersByTime(MS);
		expect(chrome.hidden).toBe(true);
	});

	it('a touch shows it and stops the idle wait: a finger hides it with a tap, not a timer', () => {
		const chrome = new ViewerChrome(MS, () => false);
		chrome.stir();
		chrome.touch();
		vi.advanceTimersByTime(10 * MS);
		expect(chrome.hidden).toBe(false);
	});

	it('a tap on the photo hides shown chrome and brings hidden chrome back', () => {
		const chrome = new ViewerChrome(MS, () => false);
		chrome.tap({ wasHidden: false, mouse: false });
		expect(chrome.hidden).toBe(true);
		chrome.tap({ wasHidden: true, mouse: false });
		expect(chrome.hidden).toBe(false);
		vi.advanceTimersByTime(10 * MS);
		expect(chrome.hidden).toBe(false);
	});

	it('a click on the photo that brings it back fades again with idle, as a mouse does', () => {
		const chrome = new ViewerChrome(MS, () => false);
		chrome.hide();
		chrome.tap({ wasHidden: true, mouse: true });
		expect(chrome.hidden).toBe(false);
		vi.advanceTimersByTime(MS);
		expect(chrome.hidden).toBe(true);
	});

	it('hide() is at once and cancels a wait that would have hidden it later', () => {
		const chrome = new ViewerChrome(MS, () => false);
		chrome.stir();
		chrome.hide();
		expect(chrome.hidden).toBe(true);
		chrome.touch();
		vi.advanceTimersByTime(10 * MS);
		expect(chrome.hidden).toBe(false);
	});

	it('stop() leaves it as it is: nothing happens by itself after', () => {
		const chrome = new ViewerChrome(MS, () => false);
		chrome.stir();
		chrome.stop();
		vi.advanceTimersByTime(10 * MS);
		expect(chrome.hidden).toBe(false);
	});
});
