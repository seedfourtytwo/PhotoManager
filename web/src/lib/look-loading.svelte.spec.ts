import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, type User } from '$lib/api';
import { DEFAULT_LOOK, look, parseLook, type Look } from '$lib/look';
import {
	api,
	chooseHome,
	chooseMode,
	forgetOldDensity,
	loadLook,
	notice,
	session,
	settings
} from './app.svelte';

vi.mock('$app/navigation', () => ({ goto: vi.fn(async () => undefined) }));

const WARM = parseLook({ theme: 'album', mode: 'light', accentHue: 30 });
const ME: User = { id: 1, username: 'c', display_name: 'C', role: 'admin', disabled: false };
const DONNA: User = { ...ME, id: 2, username: 'donna', display_name: 'Donna', role: 'member' };
const root = document.documentElement;
const cached = () => JSON.parse(localStorage.getItem('pa.look') ?? 'null') as unknown;

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason: unknown) => void;
	const promise = new Promise<T>((yes, no) => ((resolve = yes), (reject = no)));
	return { promise, resolve, reject };
}

function clean() {
	localStorage.clear();
	look.belongsTo(null);
	session.user = null;
	notice.text = '';
	vi.restoreAllMocks();
}
beforeEach(() => {
	clean();
	session.user = ME;
	look.belongsTo(ME.id);
});
afterEach(clean);

describe('loadLook', () => {
	it('shows the look the server has for this account', async () => {
		vi.spyOn(api, 'myLook').mockResolvedValue(WARM);
		await loadLook();
		expect(look.saved).toEqual(WARM);
		expect(root.getAttribute('data-look')).toBe('album');
		expect(root.getAttribute('data-theme')).toBe('light');
		expect(cached()).toEqual({ user: ME.id, sheet: WARM });
	});

	it('keeps the look on screen when the server cannot be reached', async () => {
		look.receive(WARM);
		vi.spyOn(api, 'myLook').mockRejectedValue(new TypeError('Failed to fetch'));
		await loadLook();
		expect(look.saved).toEqual(WARM);
		expect(notice.text).toBe('');
	});

	it('asks nothing with nobody signed in', async () => {
		session.user = null;
		const ask = vi.spyOn(api, 'myLook');
		await loadLook();
		expect(ask).not.toHaveBeenCalled();
	});

	it('does not leave the last account’s look for the next one when the server cannot be reached', async () => {
		look.receive(WARM); // on screen and cached for me
		session.user = DONNA; // she signs in on this device
		vi.spyOn(api, 'myLook').mockRejectedValue(new TypeError('Failed to fetch'));
		await loadLook();
		expect(look.saved).toEqual(DEFAULT_LOOK);
		expect(root.getAttribute('data-look')).toBeNull();
		expect(cached()).toBeNull();
	});

	it('drops an answer that arrives after a newer choice', async () => {
		const slow = deferred<Look>();
		vi.spyOn(api, 'myLook').mockReturnValue(slow.promise);
		vi.spyOn(api, 'setMyMode').mockImplementation(async (mode) => ({ ...DEFAULT_LOOK, mode }));
		const loading = loadLook();
		await chooseMode('light');
		slow.resolve(DEFAULT_LOOK); // the look as it was before the choice
		await loading;
		expect(look.saved.mode).toBe('light');
	});

	it('drops an answer that was asked before a save in the look form', async () => {
		const slow = deferred<Look>();
		vi.spyOn(api, 'myLook').mockReturnValue(slow.promise);
		const loading = loadLook();
		look.receive(WARM); // what LookForm does with the saved sheet of one's own account
		slow.resolve(DEFAULT_LOOK); // the look as it was before the save
		await loading;
		expect(look.saved).toEqual(WARM);
		expect(cached()).toEqual({ user: ME.id, sheet: WARM });
	});

	it('drops an answer for an account that has signed out meanwhile', async () => {
		const slow = deferred<Look>();
		vi.spyOn(api, 'myLook').mockReturnValue(slow.promise);
		vi.spyOn(api, 'logout').mockResolvedValue(undefined);
		const loading = loadLook();
		await session.signOut();
		slow.resolve(WARM);
		await loading;
		expect(look.saved).toEqual(DEFAULT_LOOK);
		expect(cached()).toBeNull();
	});
});

describe('the old per-browser pa.theme setting', () => {
	const sending = () =>
		vi.spyOn(api, 'setMyMode').mockImplementation(async (mode) => ({ ...DEFAULT_LOOK, mode }));

	it('becomes the mode of an account that has no look yet, once, and is then forgotten', async () => {
		localStorage.setItem('pa.theme', 'light');
		const ask = vi.spyOn(api, 'myLook').mockResolvedValue(DEFAULT_LOOK);
		const send = sending();

		await loadLook();

		expect(send).toHaveBeenCalledExactlyOnceWith('light');
		expect(look.saved.mode).toBe('light');
		expect(localStorage.getItem('pa.theme')).toBeNull();

		ask.mockResolvedValue({ ...DEFAULT_LOOK, mode: 'light' });
		await loadLook();
		expect(send).toHaveBeenCalledTimes(1);
	});

	it.each<[string, Look]>([
		['a mode chosen on another device', { ...DEFAULT_LOOK, mode: 'system' }],
		['a look an admin has set', parseLook({ theme: 'album', accentHue: 30 })]
	])('does not overwrite %s: it is only forgotten', async (_, theirs) => {
		localStorage.setItem('pa.theme', 'light');
		vi.spyOn(api, 'myLook').mockResolvedValue(theirs);
		const send = sending();

		await loadLook();

		expect(send).not.toHaveBeenCalled();
		expect(look.saved).toEqual(theirs);
		expect(root.getAttribute('data-theme')).toBe(theirs.mode === 'system' ? null : theirs.mode);
		expect(localStorage.getItem('pa.theme')).toBeNull();
	});

	it('sends nothing when it is the mode the account has anyway', async () => {
		localStorage.setItem('pa.theme', 'dark');
		vi.spyOn(api, 'myLook').mockResolvedValue(DEFAULT_LOOK);
		const send = sending();
		await loadLook();
		expect(send).not.toHaveBeenCalled();
		expect(localStorage.getItem('pa.theme')).toBeNull();
	});

	it('is kept for the next try when sending it fails', async () => {
		localStorage.setItem('pa.theme', 'light');
		vi.spyOn(api, 'myLook').mockResolvedValue(DEFAULT_LOOK);
		vi.spyOn(api, 'setMyMode').mockRejectedValue(new TypeError('Failed to fetch'));
		await loadLook();
		expect(localStorage.getItem('pa.theme')).toBe('light');
	});

	it('is kept for the next try when the account’s look cannot be fetched', async () => {
		localStorage.setItem('pa.theme', 'light');
		vi.spyOn(api, 'myLook').mockRejectedValue(new TypeError('Failed to fetch'));
		const send = sending();
		await loadLook();
		expect(send).not.toHaveBeenCalled();
		expect(localStorage.getItem('pa.theme')).toBe('light');
	});
});

describe('chooseHome', () => {
	it('shows the choice at once and saves it on the account', async () => {
		const saving = deferred<Look>();
		const send = vi.spyOn(api, 'setMyHome').mockReturnValue(saving.promise);
		const choosing = chooseHome(['pinned', 'years']);
		expect(look.saved.homeSections).toEqual(['pinned', 'years']);
		expect(send).toHaveBeenCalledExactlyOnceWith(['pinned', 'years']);
		saving.resolve({ ...WARM, homeSections: ['pinned', 'years'] });
		await choosing;
		expect(look.saved).toEqual({ ...WARM, homeSections: ['pinned', 'years'] });
	});

	it('goes back and says why when the server refuses', async () => {
		vi.spyOn(api, 'setMyHome').mockRejectedValue(new ApiError(503, 'The library is busy'));
		await chooseHome(['years']);
		expect(look.saved.homeSections).toEqual(DEFAULT_LOOK.homeSections);
		expect(notice.text).toBe('The library is busy');
	});
});

describe('chooseMode', () => {
	it('changes the screen at once and saves the mode on the account', async () => {
		const saving = deferred<Look>();
		const send = vi.spyOn(api, 'setMyMode').mockReturnValue(saving.promise);
		const choosing = chooseMode('light');
		expect(root.getAttribute('data-theme')).toBe('light');
		expect(send).toHaveBeenCalledExactlyOnceWith('light');
		saving.resolve({ ...WARM, mode: 'light' });
		await choosing;
		expect(look.saved).toEqual({ ...WARM, mode: 'light' });
	});

	it('goes back and says why when the server refuses', async () => {
		vi.spyOn(api, 'setMyMode').mockRejectedValue(new ApiError(503, 'The library is busy'));
		await chooseMode('light');
		expect(look.saved.mode).toBe('dark');
		expect(root.getAttribute('data-theme')).toBe('dark');
		expect(notice.text).toBe('The library is busy');
	});

	it('goes back to the mode the server has when two choices in a row are refused', async () => {
		look.receive(DEFAULT_LOOK);
		const first = deferred<Look>();
		const second = deferred<Look>();
		vi.spyOn(api, 'setMyMode')
			.mockReturnValueOnce(first.promise)
			.mockReturnValueOnce(second.promise);
		const choosing = [chooseMode('light'), chooseMode('system')];
		first.reject(new ApiError(503, 'The library is busy'));
		second.reject(new ApiError(503, 'The library is busy'));
		await Promise.all(choosing);
		expect(look.saved.mode).toBe('dark'); // never 'light': the server did not take that either
		expect(root.getAttribute('data-theme')).toBe('dark');
		expect(cached()).toEqual({ user: ME.id, sheet: DEFAULT_LOOK });
	});

	it('does not cache a mode before the server has taken it', async () => {
		look.receive(DEFAULT_LOOK);
		const saving = deferred<Look>();
		vi.spyOn(api, 'setMyMode').mockReturnValue(saving.promise);
		const choosing = chooseMode('light');
		expect(cached()).toEqual({ user: ME.id, sheet: DEFAULT_LOOK });
		saving.resolve({ ...DEFAULT_LOOK, mode: 'light' });
		await choosing;
		expect(cached()).toEqual({ user: ME.id, sheet: { ...DEFAULT_LOOK, mode: 'light' } });
	});

	it('wins over an old pa.theme setting that was never sent', async () => {
		localStorage.setItem('pa.theme', 'light');
		vi.spyOn(api, 'setMyMode').mockImplementation(async (mode) => ({ ...DEFAULT_LOOK, mode }));
		await chooseMode('system');
		expect(localStorage.getItem('pa.theme')).toBeNull();
		expect(look.saved.mode).toBe('system');
	});
});

describe('leaving (a shared device)', () => {
	it('signing out goes back to the defaults and forgets the cached look', async () => {
		look.receive(WARM);
		expect(root.getAttribute('data-look')).toBe('album');
		vi.spyOn(api, 'logout').mockResolvedValue(undefined);
		await session.signOut();
		expect(look.saved).toEqual(DEFAULT_LOOK);
		expect(root.getAttribute('data-look')).toBeNull();
		expect(root.getAttribute('data-theme')).toBe('dark');
		expect(cached()).toBeNull();
	});

	it('so does a session that is lost, and a look that was being tried ends with it', () => {
		look.receive(WARM);
		look.try(parseLook({ accentHue: 220 }), { id: 2, name: 'Donna' });
		session.lost();
		expect(look.trial).toBeNull();
		expect(look.saved).toEqual(DEFAULT_LOOK);
		expect(root.getAttribute('data-look')).toBeNull();
		expect(root.style.getPropertyValue('--acc-h')).toBe('');
		expect(cached()).toBeNull();
	});
});

describe('the look’s dials that the grid reads', () => {
	it('the look’s thumb size is the grid size, and so is that of a look being tried', () => {
		expect(settings.thumbSize).toBe('medium');
		look.receive(parseLook({ thumbSize: 'large' }));
		expect(settings.thumbSize).toBe('large');
		look.try(parseLook({ thumbSize: 'small' }), { id: 2, name: 'Donna' });
		expect(settings.thumbSize).toBe('small');
	});

	it('a photo size once chosen on this device is forgotten, so the look decides again', () => {
		localStorage.setItem('pa.density', 'compact');
		look.receive(parseLook({ thumbSize: 'large' }));
		forgetOldDensity();
		expect(localStorage.getItem('pa.density')).toBeNull();
		expect(settings.thumbSize).toBe('large');
	});

	it('forgetting it does not throw where storage is blocked', () => {
		vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
			throw new DOMException('blocked', 'SecurityError');
		});
		expect(forgetOldDensity).not.toThrow();
	});

	it('the look’s photo gap is the grid gap; left to the theme it is 3', () => {
		expect(settings.gap).toBe(3);
		look.receive(parseLook({ photoGap: 0 }));
		expect(settings.gap).toBe(0);
		look.try(parseLook({ photoGap: 8 }), { id: 2, name: 'Donna' });
		expect(settings.gap).toBe(8);
	});
});
