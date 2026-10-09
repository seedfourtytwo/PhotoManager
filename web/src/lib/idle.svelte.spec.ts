import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Idle } from './idle.svelte';

const MS = 1000;

beforeEach(() => {
	vi.useFakeTimers();
});
afterEach(() => {
	vi.useRealTimers();
});

describe('Idle', () => {
	it.each([true, false])('starts as it is told (idle: %s) and stays so untouched', (idle) => {
		const chrome = new Idle(MS, { idle, inUse: () => false });
		vi.advanceTimersByTime(10 * MS);
		expect(chrome.idle).toBe(idle);
	});

	it('is awake after wake() and idle once the time has passed', () => {
		const chrome = new Idle(MS, { idle: true, inUse: () => false });
		chrome.wake();
		expect(chrome.idle).toBe(false);
		vi.advanceTimersByTime(MS - 1);
		expect(chrome.idle).toBe(false);
		vi.advanceTimersByTime(1);
		expect(chrome.idle).toBe(true);
	});

	it('every wake() starts the wait again', () => {
		const chrome = new Idle(MS, { idle: true, inUse: () => false });
		chrome.wake();
		vi.advanceTimersByTime(MS - 1);
		chrome.wake();
		vi.advanceTimersByTime(MS - 1);
		expect(chrome.idle).toBe(false);
		vi.advanceTimersByTime(1);
		expect(chrome.idle).toBe(true);
	});

	it('stays awake while in use: it asks again each time the wait ends', () => {
		let inUse = true;
		const chrome = new Idle(MS, { idle: true, inUse: () => inUse });
		chrome.wake();
		vi.advanceTimersByTime(2.5 * MS);
		expect(chrome.idle).toBe(false);
		inUse = false;
		vi.advanceTimersByTime(MS / 2 - 1);
		expect(chrome.idle).toBe(false);
		vi.advanceTimersByTime(1);
		expect(chrome.idle).toBe(true);
	});

	it('hide() is idle at once and for good: the wait that was running is dropped', () => {
		const chrome = new Idle(MS, { idle: false, inUse: () => true });
		chrome.wake();
		chrome.hide();
		expect(chrome.idle).toBe(true);
		vi.advanceTimersByTime(10 * MS);
		expect(chrome.idle).toBe(true);
	});

	it('stop() drops the wait: what is awake stays awake', () => {
		const chrome = new Idle(MS, { idle: true, inUse: () => false });
		chrome.wake();
		chrome.stop();
		vi.advanceTimersByTime(10 * MS);
		expect(chrome.idle).toBe(false);
	});
});
