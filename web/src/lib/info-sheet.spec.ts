import { beforeEach, describe, expect, it, vi } from 'vitest';
import { pushState } from '$app/navigation';
import { page } from '$app/state';
import { stepBack } from './history-step';
import { InfoSheet } from './info-sheet.svelte';

vi.mock('$app/navigation', () => ({ pushState: vi.fn() }));
vi.mock('$app/state', () => ({ page: { state: {} } }));
vi.mock('./history-step', () => ({
	stepsGone: vi.fn(() => Promise.resolve()),
	stepBack: vi.fn()
}));

describe('the Info sheet’s history step (phone)', () => {
	/** The entries under the current one, as far as these tests need them: their states. */
	let under: App.PageState[] = [];
	let sheet: InfoSheet;

	beforeEach(() => {
		vi.clearAllMocks();
		under = [];
		page.state = { photo: 5, pushed: true };
		sheet = new InfoSheet();
		vi.mocked(pushState).mockImplementation((_url, state) => {
			under.push(page.state);
			page.state = state;
		});
		// Going back takes the browser a moment.
		vi.mocked(stepBack).mockImplementation(async () => {
			await new Promise((r) => setTimeout(r, 5));
			page.state = under.pop() ?? {};
		});
	});

	it('opens at once and adds one entry that keeps what the photo’s entry holds', async () => {
		const done = sheet.show(true);
		expect(sheet.open).toBe(true);
		await done;
		expect(pushState).toHaveBeenCalledExactlyOnceWith('', { photo: 5, pushed: true, info: true });
		expect(sheet.open).toBe(true);
	});

	it('closed by its own control it hides at once and takes its entry out again', async () => {
		await sheet.show(true);
		const done = sheet.show(false);
		expect(sheet.open).toBe(false);
		await done;
		expect(stepBack).toHaveBeenCalledOnce();
		expect(page.state).toEqual({ photo: 5, pushed: true });
		expect(sheet.open).toBe(false);
	});

	it('Back leaves its entry, and that closes it', async () => {
		await sheet.show(true);
		page.state = under.pop()!;
		expect(sheet.open).toBe(false);
		// Nothing is left to take out.
		await sheet.show(false);
		expect(stepBack).not.toHaveBeenCalled();
	});

	it('Forward onto its entry opens it again', async () => {
		page.state = { photo: 5, pushed: true, info: true };
		expect(sheet.open).toBe(true);
	});

	it('asked to close when it is not open, it goes nowhere', async () => {
		await sheet.show(false);
		expect(stepBack).not.toHaveBeenCalled();
		expect(pushState).not.toHaveBeenCalled();
	});

	it.each([
		[5, true],
		[6, false]
	])(
		'%i presses faster than the history follows: it ends as last asked, with no entry too many',
		async (presses, open) => {
			let last = Promise.resolve();
			for (let i = 0; i < presses; i++) last = sheet.show(!sheet.open);
			expect(sheet.open).toBe(open);
			await last;
			expect(sheet.open).toBe(open);
			expect(page.state.info === true).toBe(open);
			expect(under).toHaveLength(open ? 1 : 0);
		}
	);

	it('asked twice to close, it goes back once', async () => {
		await sheet.show(true);
		await Promise.all([sheet.show(false), sheet.show(false)]);
		expect(stepBack).toHaveBeenCalledOnce();
	});

	it('opens and closes without a history where there is no router (a component on its own)', async () => {
		vi.mocked(pushState).mockImplementation(() => {
			throw new Error('Cannot call pushState(...) before router is initialized');
		});
		await sheet.show(true);
		expect(sheet.open).toBe(true);
		await sheet.show(false);
		expect(sheet.open).toBe(false);
		expect(stepBack).not.toHaveBeenCalled();
	});
});
