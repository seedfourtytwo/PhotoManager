import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { DEFAULT_LOOK, parseLook } from './sheet';
import { LookState } from './look.svelte';

const root = document.documentElement;
const WARM = parseLook({ theme: 'album', mode: 'light', accentHue: 30 });
const COOL = parseLook({ accentHue: 220, textScale: 1.2 });
const donna = { id: 7, name: 'Donna' };

const onPage = () => ({
	look: root.getAttribute('data-look'),
	mode: root.getAttribute('data-theme'),
	hue: root.style.getPropertyValue('--acc-h'),
	scale: root.style.getPropertyValue('--text-scale')
});

function clean() {
	localStorage.clear();
	root.removeAttribute('data-look');
	root.removeAttribute('data-theme');
	root.removeAttribute('style');
}
beforeEach(clean);
afterEach(clean);

describe('the look in the app', () => {
	it('starts from the cached sheet', () => {
		localStorage.setItem('pa.look', JSON.stringify(WARM));
		expect(new LookState().shown).toEqual(WARM);
	});

	it('a received sheet is shown, cached and set on the page', () => {
		const look = new LookState();
		look.receive(WARM);
		expect(look.saved).toEqual(WARM);
		expect(look.shown).toEqual(WARM);
		expect(onPage()).toEqual({ look: 'album', mode: 'light', hue: '30', scale: '' });
		expect(JSON.parse(localStorage.getItem('pa.look')!)).toEqual(WARM);
	});

	it('a broken sheet from the server shows the defaults', () => {
		const look = new LookState();
		look.receive(WARM);
		look.receive({ mode: 'light', css: 'body { display: none }' });
		expect(look.shown).toEqual(DEFAULT_LOOK);
		expect(onPage()).toEqual({ look: null, mode: 'dark', hue: '', scale: '' });
	});

	it('a trial is shown without being cached and ends on Stop trying', () => {
		const look = new LookState();
		look.receive(WARM);
		look.try(COOL, donna);
		expect(look.shown).toEqual(COOL);
		expect(look.saved).toEqual(WARM);
		expect(look.trial).toEqual({ sheet: COOL, who: donna });
		expect(onPage()).toEqual({ look: null, mode: 'dark', hue: '220', scale: '1.2' });
		expect(JSON.parse(localStorage.getItem('pa.look')!)).toEqual(WARM);

		look.stopTrying();
		expect(look.trial).toBeNull();
		expect(look.shown).toEqual(WARM);
		expect(onPage()).toEqual({ look: 'album', mode: 'light', hue: '30', scale: '' });
	});

	it('a sheet received while trying waits behind the trial', () => {
		const look = new LookState();
		look.try(COOL, donna);
		look.receive(WARM);
		expect(look.shown).toEqual(COOL);
		expect(onPage().hue).toBe('220');
		expect(JSON.parse(localStorage.getItem('pa.look')!)).toEqual(WARM);
		look.stopTrying();
		expect(onPage()).toEqual({ look: 'album', mode: 'light', hue: '30', scale: '' });
	});

	it('a trial does not outlive the page: a new start shows the saved look', () => {
		const first = new LookState();
		first.receive(WARM);
		first.try(COOL, donna);
		const reloaded = new LookState();
		expect(reloaded.trial).toBeNull();
		expect(reloaded.shown).toEqual(WARM);
	});

	it('the trial is a copy: changing the form afterwards does not change the screen', () => {
		const look = new LookState();
		const sheet = parseLook({ collectionsRows: ['albums'] });
		look.try(sheet, donna);
		sheet.collectionsRows.push('people');
		expect(look.shown.collectionsRows).toEqual(['albums']);
	});
});
