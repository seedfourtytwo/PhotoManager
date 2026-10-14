import { afterEach, describe, expect, it } from 'vitest';
import { parseLook } from './look';
import { Arrival, HOME, landing, mayLand } from './start-page.svelte';

const url = (href: string) => new URL(href, 'http://photos.test');
const today = parseLook({});
const library = parseLook({ startPage: 'library' });
const noHome = parseLook({ showToday: false });

describe('landing: where the first page of a session goes', () => {
	it('a bare / opens Home when the look starts on Home (the default)', () => {
		expect(landing(url('/'), today)).toBe(HOME);
		expect(HOME).toBe('/home');
	});
	it('stays on Library when the look starts there, or does not show Home', () => {
		expect(landing(url('/'), library)).toBeNull();
		expect(landing(url('/'), noHome)).toBeNull();
		// a sheet that says both (never stored: showToday off forces Library) still stays
		expect(landing(url('/'), { showToday: false, startPage: 'today' })).toBeNull();
	});
	it.each(['/?year=2019', '/?photo=12', '/calendar', '/albums/3', '/home', '/search?q=sea'])(
		'%s is a page someone asked for: it stays',
		(href) => {
			expect(landing(url(href), today)).toBeNull();
		}
	);
	it('a link to the page itself (#main) still counts as a bare /', () => {
		expect(landing(url('/#main'), today)).toBe(HOME);
	});
	it('mayLand: only a bare / waits for the decision', () => {
		expect(mayLand(url('/'))).toBe(true);
		expect(mayLand(url('/?year=2019'))).toBe(false);
		expect(mayLand(url('/home'))).toBe(false);
	});
});

/** A tab's sessionStorage, or one that refuses (private mode, blocked site data). */
function storage(refuse = false) {
	const kept = new Map<string, string>();
	const no = () => {
		throw new DOMException('blocked', 'SecurityError');
	};
	return {
		kept,
		getItem: (key: string) => (refuse ? no() : (kept.get(key) ?? null)),
		setItem: (key: string, value: string) => (refuse ? no() : void kept.set(key, value)),
		removeItem: (key: string) => (refuse ? no() : void kept.delete(key))
	};
}

describe('Arrival: once per tab', () => {
	afterEach(() => sessionStorage.clear());

	it('a new tab has not arrived; marking it is kept for the tab (a reload is not a new start)', () => {
		const tab = storage();
		const first = new Arrival(tab);
		expect(first.done).toBe(false);
		first.mark();
		expect(first.done).toBe(true);
		expect(new Arrival(tab).done).toBe(true);
	});
	it('forgetting it (signing out) lets the next sign-in start again', () => {
		const tab = storage();
		const arrival = new Arrival(tab);
		arrival.mark();
		arrival.forget();
		expect(arrival.done).toBe(false);
		expect(new Arrival(tab).done).toBe(false);
	});
	it('without storage it still works for as long as the page lives, and throws nothing', () => {
		const arrival = new Arrival(storage(true));
		expect(arrival.done).toBe(false);
		arrival.mark();
		expect(arrival.done).toBe(true);
		arrival.forget();
		expect(arrival.done).toBe(false);
	});
	it('the app’s own uses the tab’s sessionStorage', () => {
		new Arrival().mark();
		expect(new Arrival().done).toBe(true);
	});
});
