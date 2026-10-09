import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '$lib/api';
import { DEFAULT_LOOK, look, parseLook, type Look } from '$lib/look';
import { api, chooseMode, loadLook, notice, settings } from './app.svelte';

vi.mock('$app/navigation', () => ({ goto: vi.fn(async () => undefined) }));

const WARM = parseLook({ theme: 'album', mode: 'light', accentHue: 30 });
const root = document.documentElement;

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason: unknown) => void;
	const promise = new Promise<T>((yes, no) => ((resolve = yes), (reject = no)));
	return { promise, resolve, reject };
}

function clean() {
	localStorage.clear();
	look.stopTrying();
	look.receive(DEFAULT_LOOK);
	localStorage.clear();
	notice.text = '';
	vi.restoreAllMocks();
}
beforeEach(clean);
afterEach(clean);

describe('loadLook', () => {
	it('shows the look the server has for this account', async () => {
		vi.spyOn(api, 'myLook').mockResolvedValue(WARM);
		await loadLook();
		expect(look.saved).toEqual(WARM);
		expect(root.getAttribute('data-look')).toBe('album');
		expect(root.getAttribute('data-theme')).toBe('light');
	});

	it('keeps the look on screen when the server cannot be reached', async () => {
		look.receive(WARM);
		vi.spyOn(api, 'myLook').mockRejectedValue(new TypeError('Failed to fetch'));
		await loadLook();
		expect(look.saved).toEqual(WARM);
		expect(notice.text).toBe('');
	});

	it('sends the old pa.theme setting as the mode once, then forgets it', async () => {
		localStorage.setItem('pa.theme', 'light');
		const ask = vi.spyOn(api, 'myLook');
		const send = vi
			.spyOn(api, 'setMyMode')
			.mockImplementation(async (mode) => ({ ...DEFAULT_LOOK, mode }));

		await loadLook();

		expect(send).toHaveBeenCalledExactlyOnceWith('light');
		expect(ask).not.toHaveBeenCalled();
		expect(look.saved.mode).toBe('light');
		expect(localStorage.getItem('pa.theme')).toBeNull();

		ask.mockResolvedValue({ ...DEFAULT_LOOK, mode: 'light' });
		await loadLook();
		expect(send).toHaveBeenCalledTimes(1);
	});

	it('keeps the old setting for the next try when sending it fails', async () => {
		localStorage.setItem('pa.theme', 'light');
		vi.spyOn(api, 'setMyMode').mockRejectedValue(new TypeError('Failed to fetch'));
		await loadLook();
		expect(localStorage.getItem('pa.theme')).toBe('light');
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

	it('wins over an old pa.theme setting that was never sent', async () => {
		localStorage.setItem('pa.theme', 'light');
		vi.spyOn(api, 'setMyMode').mockImplementation(async (mode) => ({ ...DEFAULT_LOOK, mode }));
		await chooseMode('system');
		expect(localStorage.getItem('pa.theme')).toBeNull();
		expect(look.saved.mode).toBe('system');
	});
});

describe('the look’s dials that the grid reads', () => {
	it('the look’s thumb size is the grid size until one is chosen on this device', () => {
		expect(settings.density).toBe('comfortable');
		look.receive(parseLook({ thumbSize: 'large' }));
		expect(settings.density).toBe('large');
		look.receive(parseLook({ thumbSize: 'small' }));
		expect(settings.density).toBe('compact');
		settings.setDensity('comfortable');
		expect(settings.density).toBe('comfortable');
		expect(localStorage.getItem('pa.density')).toBe('comfortable');
	});

	it('the look’s photo gap is the grid gap; left to the theme it is 3', () => {
		expect(settings.gap).toBe(3);
		look.receive(parseLook({ photoGap: 0 }));
		expect(settings.gap).toBe(0);
		look.try(parseLook({ photoGap: 8 }), { id: 2, name: 'Donna' });
		expect(settings.gap).toBe(8);
	});
});
