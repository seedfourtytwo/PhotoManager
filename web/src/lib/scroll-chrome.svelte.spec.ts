import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
	decide,
	HIDE_AFTER,
	NEAR_TOP,
	ScrollChrome,
	SHOW_AFTER,
	SHOWN,
	type Track
} from './scroll-chrome.svelte';

const MAX = 5000;
/** The track after the page passed through each of `ys` in turn. */
function through(ys: number[], from: Track = SHOWN, held = false, max = MAX): Track {
	return ys.reduce((track, y) => decide(track, { y, max, held }), from);
}

describe('decide', () => {
	it('stays shown near the top, however it is scrolled', () => {
		expect(through([0, NEAR_TOP]).chrome).toBe('shown');
		expect(through([0, 400, NEAR_TOP - 1]).chrome).toBe('shown');
	});

	/** Shown at `y`, counting from there: it hid on the way down and came back up to `y`. */
	const shownAt = (y: number) => through([y + 100, y]);

	it(`hides once the page has gone ${HIDE_AFTER} px down, not before`, () => {
		expect(shownAt(300).chrome).toBe('shown');
		expect(through([300 + HIDE_AFTER - 1], shownAt(300)).chrome).toBe('shown');
		expect(through([300 + HIDE_AFTER], shownAt(300)).chrome).toBe('away');
	});

	it('adds up small steps down', () => {
		expect(through([304, 308, 312], shownAt(300)).chrome).toBe('away');
	});

	it(`comes back on ${SHOW_AFTER} px up, and not on a smaller twitch`, () => {
		const away = through([100, 400]);
		expect(away.chrome).toBe('away');
		expect(through([400 - SHOW_AFTER + 1], away).chrome).toBe('away');
		expect(through([400 - SHOW_AFTER], away).chrome).toBe('shown');
	});

	it('counts the way up from the lowest point, not from where it hid', () => {
		const away = through([100, 400, 900]);
		expect(through([900 - SHOW_AFTER + 1], away).chrome).toBe('away');
		expect(through([900 - SHOW_AFTER], away).chrome).toBe('shown');
	});

	it('counts the way down from the highest place on the page since it came back', () => {
		const back = shownAt(300);
		expect(through([310, 305, 300 + HIDE_AFTER - 1], back).chrome).toBe('shown');
		expect(through([310, 305, 300 + HIDE_AFTER], back).chrome).toBe('away');
		expect(through([290, 290 + HIDE_AFTER - 1], back).chrome).toBe('shown');
	});

	it('a bounce above the top (negative scroll) shows it', () => {
		expect(through([-30], through([100, 400])).chrome).toBe('shown');
	});

	it('a bounce past the bottom does not bring it back on the way home', () => {
		const away = through([100, MAX]);
		expect(through([MAX + 40, MAX + 10, MAX], away).chrome).toBe('away');
	});

	it('a page shorter than the screen always shows it', () => {
		expect(through([0, 300], SHOWN, false, 0).chrome).toBe('shown');
	});

	it('a page that shrank under it (a resize) counts from its new end', () => {
		const away = through([100, 2000]);
		// The page is now 1000 high: 2000 reads as 1000, and only going above that shows it.
		expect(through([1000], away, false, 1000).chrome).toBe('away');
		expect(through([1000 - SHOW_AFTER], away, false, 1000).chrome).toBe('shown');
	});

	it('held (focus inside, a menu or dialog open) it shows and never hides', () => {
		expect(through([400], through([100, 400]), true).chrome).toBe('shown');
		expect(through([100, 400, 2000], SHOWN, true).chrome).toBe('shown');
	});

	it('let go, it hides only after a fresh run down from where it was held', () => {
		const held = through([100, 2000], SHOWN, true);
		expect(through([2000 + HIDE_AFTER - 1], held).chrome).toBe('shown');
		expect(through([2000 + HIDE_AFTER], held).chrome).toBe('away');
	});
});

describe('ScrollChrome', () => {
	let bar: HTMLElement;
	let tall: HTMLElement;
	let chrome: ScrollChrome;
	let stop: () => void;
	const frame = () => new Promise((done) => requestAnimationFrame(() => done(undefined)));
	const scrollTo = async (y: number) => {
		window.scrollTo(0, y);
		await new Promise((done) => window.addEventListener('scroll', done, { once: true }));
		await frame();
		await frame();
	};
	const root = () => document.documentElement.dataset.chrome;

	beforeEach(async () => {
		bar = Object.assign(document.createElement('nav'), {
			innerHTML: '<a href="#x">Library</a>'
		});
		tall = document.createElement('div');
		tall.style.height = '6000px';
		document.body.append(bar, tall);
		window.scrollTo(0, 0);
		await frame();
		chrome = new ScrollChrome(() => bar);
		stop = chrome.watch();
	});
	afterEach(() => {
		stop();
		bar.remove();
		tall.remove();
		document.querySelector('#menu')?.remove();
		window.scrollTo(0, 0);
	});

	it('marks the root away after a scroll down and takes the mark off on the way up', async () => {
		expect(root()).toBeUndefined();
		await scrollTo(600);
		expect(chrome.chrome).toBe('away');
		expect(root()).toBe('away');
		await scrollTo(500);
		expect(chrome.chrome).toBe('shown');
		expect(root()).toBeUndefined();
	});

	it('focus moving into the bar brings it back at once', async () => {
		await scrollTo(600);
		expect(root()).toBe('away');
		bar.querySelector('a')!.focus({ preventScroll: true });
		expect(chrome.chrome).toBe('shown');
		expect(root()).toBeUndefined();
		await scrollTo(1200);
		expect(chrome.chrome).toBe('shown');
	});

	it('an open menu keeps it shown while the page scrolls', async () => {
		const menu = Object.assign(document.createElement('button'), { id: 'menu' });
		menu.setAttribute('aria-expanded', 'true');
		document.body.append(menu);
		await scrollTo(600);
		expect(chrome.chrome).toBe('shown');
		menu.setAttribute('aria-expanded', 'false');
		await scrollTo(1200);
		expect(chrome.chrome).toBe('away');
	});

	it('reset() (a new page) shows it', async () => {
		await scrollTo(600);
		chrome.reset();
		expect(chrome.chrome).toBe('shown');
		expect(root()).toBeUndefined();
	});

	it('stopping takes the mark off and stops listening', async () => {
		await scrollTo(600);
		stop();
		expect(root()).toBeUndefined();
		await scrollTo(300);
		await scrollTo(1500);
		expect(root()).toBeUndefined();
	});
});
