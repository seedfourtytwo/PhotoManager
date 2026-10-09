import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { DEFAULT_LOOK, parseLook } from './sheet';
import { LookState } from './look.svelte';

const root = document.documentElement;
const WARM = parseLook({ theme: 'album', mode: 'light', accentHue: 30 });
const COOL = parseLook({ accentHue: 220, textScale: 1.2 });
const donna = { id: 7, name: 'Donna' };
const ME = 1;

const onPage = () => ({
	look: root.getAttribute('data-look'),
	mode: root.getAttribute('data-theme'),
	hue: root.style.getPropertyValue('--acc-h'),
	scale: root.style.getPropertyValue('--text-scale')
});
const DEFAULTS_ON_PAGE = { look: null, mode: 'dark', hue: '', scale: '' };
const WARM_ON_PAGE = { look: 'album', mode: 'light', hue: '30', scale: '' };

const cached = () => JSON.parse(localStorage.getItem('pa.look') ?? 'null') as unknown;
const cacheFor = (user: number, sheet: unknown) =>
	localStorage.setItem('pa.look', JSON.stringify({ user, sheet }));

/** The look of the account signed in here. */
function mine() {
	const look = new LookState();
	look.belongsTo(ME);
	return look;
}

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
		cacheFor(ME, WARM);
		expect(new LookState().shown).toEqual(WARM);
	});

	it('a received sheet is shown, cached for this account and set on the page', () => {
		const look = mine();
		look.receive(WARM);
		expect(look.saved).toEqual(WARM);
		expect(look.shown).toEqual(WARM);
		expect(onPage()).toEqual(WARM_ON_PAGE);
		expect(cached()).toEqual({ user: ME, sheet: WARM });
	});

	it('something from the server that is no sheet shows the defaults', () => {
		const look = mine();
		look.receive(WARM);
		look.receive('body { display: none }');
		expect(look.shown).toEqual(DEFAULT_LOOK);
		expect(onPage()).toEqual(DEFAULTS_ON_PAGE);
	});

	it('a sheet from a newer server keeps every field this build knows', () => {
		const look = mine();
		look.receive({ ...WARM, theme: 'added-in-a-newer-version', addedLater: true });
		expect(look.shown).toEqual({ ...WARM, theme: 'safelight' });
		expect(onPage()).toEqual({ ...WARM_ON_PAGE, look: null });
	});

	it('a trial is shown without being cached and ends on Stop trying', () => {
		const look = mine();
		look.receive(WARM);
		look.try(COOL, donna);
		expect(look.shown).toEqual(COOL);
		expect(look.saved).toEqual(WARM);
		expect(look.trial).toEqual({ sheet: COOL, who: donna });
		expect(onPage()).toEqual({ look: null, mode: 'dark', hue: '220', scale: '1.2' });
		expect(cached()).toEqual({ user: ME, sheet: WARM });

		look.stopTrying();
		expect(look.trial).toBeNull();
		expect(look.shown).toEqual(WARM);
		expect(onPage()).toEqual(WARM_ON_PAGE);
	});

	it('a sheet received while trying waits behind the trial', () => {
		const look = mine();
		look.try(COOL, donna);
		look.receive(WARM);
		expect(look.shown).toEqual(COOL);
		expect(onPage().hue).toBe('220');
		expect(cached()).toEqual({ user: ME, sheet: WARM });
		look.stopTrying();
		expect(onPage()).toEqual(WARM_ON_PAGE);
	});

	it('a trial does not outlive the page: a new start shows the saved look', () => {
		const first = mine();
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

describe('whose look it is (a shared device)', () => {
	it('keeps the cached look for the account it was cached for', () => {
		cacheFor(ME, WARM);
		const look = new LookState();
		look.show();
		look.belongsTo(ME);
		expect(look.shown).toEqual(WARM);
		expect(onPage()).toEqual(WARM_ON_PAGE);
		expect(cached()).toEqual({ user: ME, sheet: WARM });
	});

	it('drops a look cached for another account when someone else signs in', () => {
		cacheFor(3, WARM);
		const look = new LookState();
		look.show();
		expect(onPage()).toEqual(WARM_ON_PAGE); // painted before anyone was known
		look.belongsTo(ME);
		expect(look.shown).toEqual(DEFAULT_LOOK);
		expect(onPage()).toEqual(DEFAULTS_ON_PAGE);
		expect(cached()).toBeNull();
	});

	it('goes back to the defaults and forgets the cache when the account signs out', () => {
		const look = mine();
		look.receive(WARM);
		look.try(COOL, donna);
		look.belongsTo(null);
		expect(look.trial).toBeNull();
		expect(look.shown).toEqual(DEFAULT_LOOK);
		expect(onPage()).toEqual(DEFAULTS_ON_PAGE);
		expect(cached()).toBeNull();
	});

	it('shows the next account the defaults, not the last one’s look, until its own arrives', () => {
		const look = mine();
		look.receive(WARM);
		look.belongsTo(2); // without a sign-out in between: the session was swapped
		expect(look.shown).toEqual(DEFAULT_LOOK);
		expect(cached()).toBeNull();
		look.receive(COOL);
		expect(cached()).toEqual({ user: 2, sheet: COOL });
	});

	it('caches nothing while nobody is signed in', () => {
		const look = new LookState();
		look.receive(WARM);
		expect(look.shown).toEqual(WARM);
		expect(cached()).toBeNull();
	});

	it('keeps the old pa.theme setting as the mode of the sign-in page', () => {
		localStorage.setItem('pa.theme', 'light');
		const look = mine();
		look.receive(WARM);
		look.belongsTo(null);
		expect(look.shown).toEqual({ ...DEFAULT_LOOK, mode: 'light' });
	});

	it('drops an answer that was asked for the account before', () => {
		const look = mine();
		const asked = look.reading();
		const change = look.changing(COOL);
		look.belongsTo(2);
		asked.answer(WARM);
		change.answer(COOL);
		expect(look.shown).toEqual(DEFAULT_LOOK);
		expect(cached()).toBeNull();
	});
});

describe('the order of answers about the account’s look', () => {
	it('an answer older than one that has landed is dropped', () => {
		const look = mine();
		const first = look.reading();
		const second = look.reading();
		second.answer(WARM);
		first.answer(COOL);
		expect(look.saved).toEqual(WARM);
		expect(cached()).toEqual({ user: ME, sheet: WARM });
	});

	it('a change shows what it hopes for at once, without caching it', () => {
		const look = mine();
		look.receive(WARM);
		const change = look.changing({ ...WARM, mode: 'dark' });
		expect(look.saved.mode).toBe('dark');
		expect(onPage().mode).toBe('dark');
		expect(cached()).toEqual({ user: ME, sheet: WARM });
		change.answer({ ...WARM, mode: 'dark', accentHue: 99 }); // the server's sheet, not the hope
		expect(look.saved).toEqual({ ...WARM, mode: 'dark', accentHue: 99 });
		expect(cached()).toEqual({ user: ME, sheet: look.saved });
	});

	it('a refused change goes back to the sheet the server last gave', () => {
		const look = mine();
		look.receive(WARM);
		look.changing({ ...WARM, mode: 'dark' }).fail();
		expect(look.saved).toEqual(WARM);
		expect(onPage()).toEqual(WARM_ON_PAGE);
	});

	it('two refused changes in a row go back to it too, not to the first one’s hope', () => {
		const look = mine();
		look.receive(WARM);
		const first = look.changing({ ...WARM, mode: 'dark' });
		const second = look.changing({ ...WARM, mode: 'system' });
		first.fail();
		expect(look.saved.mode).toBe('system'); // the second is still on its way
		second.fail();
		expect(look.saved).toEqual(WARM);
		expect(onPage()).toEqual(WARM_ON_PAGE);
		expect(cached()).toEqual({ user: ME, sheet: WARM });
	});

	it('a refused change after an accepted one goes back to the accepted one', () => {
		const look = mine();
		look.receive(WARM);
		const first = look.changing({ ...WARM, mode: 'dark' });
		const second = look.changing({ ...WARM, mode: 'system' });
		first.answer({ ...WARM, mode: 'dark' });
		expect(look.saved.mode).toBe('system');
		second.fail();
		expect(look.saved).toEqual({ ...WARM, mode: 'dark' });
		expect(cached()).toEqual({ user: ME, sheet: { ...WARM, mode: 'dark' } });
	});

	it('a read asked before a change does not undo it, however late it answers', () => {
		const look = mine();
		const read = look.reading();
		const change = look.changing(COOL);
		change.answer(COOL);
		read.answer(WARM); // the sheet as it was before the change
		expect(look.saved).toEqual(COOL);
	});

	it('a read answered while a change is on its way stays behind the change’s hope', () => {
		const look = mine();
		const read = look.reading();
		const change = look.changing(COOL);
		read.answer(WARM);
		expect(look.saved).toEqual(COOL);
		change.fail();
		expect(look.saved).toEqual(WARM); // what the server last gave
	});

	it('a read asked while a change is unanswered is dropped: it may be from before', () => {
		const look = mine();
		const change = look.changing(COOL);
		const read = look.reading();
		change.answer(COOL);
		read.answer(WARM);
		expect(look.saved).toEqual(COOL);
		expect(cached()).toEqual({ user: ME, sheet: COOL });
	});

	it('a received sheet is newer than every request still out (a save in the look form)', () => {
		const look = mine();
		const read = look.reading();
		look.receive(COOL);
		read.answer(WARM);
		expect(look.saved).toEqual(COOL);
		expect(cached()).toEqual({ user: ME, sheet: COOL });
	});
});
