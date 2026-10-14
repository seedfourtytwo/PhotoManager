import { page } from 'vitest/browser';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import type { ManagedUser } from '$lib/api';
import { notice, session } from '$lib/app.svelte';
import { DEFAULT_LOOK, look, parseLook, type Look } from '$lib/look';
import LookForm from './LookForm.svelte';
import LookTrial from '../LookTrial.svelte';

const admin: ManagedUser = {
	id: 1,
	username: 'admin',
	display_name: 'C',
	role: 'admin',
	disabled: false,
	locked: false
};
const donna: ManagedUser = { ...admin, id: 2, username: 'donna', display_name: 'Donna' };
const hers = parseLook({ theme: 'album', mode: 'light', textScale: 1.15, startPage: 'library' });
const mine = parseLook({ accentHue: 120 });
const root = document.documentElement;

type Call = { method: string; url: string; body: unknown };

/** The look routes: GET answers `stored`; PUT answers what `save` makes of the body. */
function serve(stored: Look, save: (body: unknown) => { status?: number; json: unknown }) {
	const calls: Call[] = [];
	vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
		const call = {
			method: init?.method ?? 'GET',
			url: String(input),
			body: init?.body ? JSON.parse(String(init.body)) : undefined
		};
		calls.push(call);
		const { status = 200, json } = call.method === 'PUT' ? save(call.body) : { json: stored };
		return new Response(JSON.stringify(json), {
			status,
			headers: { 'content-type': 'application/json' }
		});
	});
	return calls;
}
const echo = (body: unknown) => ({ json: body });

const form = () => page.getByRole('dialog', { name: 'Look for Donna' });
const button = (name: string) => form().getByRole('button', { name, exact: true });

function clean() {
	look.stopTrying();
	look.receive(mine);
	notice.text = '';
	vi.unstubAllGlobals();
}
beforeEach(() => {
	clean();
	session.user = admin;
});
afterEach(() => {
	clean();
	session.user = null;
	localStorage.clear();
});

describe('LookForm', () => {
	it('opens on the account’s stored look', async () => {
		const calls = serve(hers, echo);
		render(LookForm, { user: donna, onclose: () => {} });
		await expect
			.element(form().getByRole('combobox', { name: 'Theme', exact: true }))
			.toHaveValue('album');
		await expect
			.element(form().getByRole('combobox', { name: 'Mode', exact: true }))
			.toHaveValue('light');
		await expect.element(form().getByRole('slider', { name: 'Text size' })).toHaveValue('1.15');
		await expect
			.element(form().getByRole('checkbox', { name: 'Accent colour: the theme’s own' }))
			.toBeChecked();
		await expect.element(form().getByRole('slider', { name: 'Accent hue' })).toBeDisabled();
		expect(calls).toEqual([{ method: 'GET', url: '/api/admin/accounts/2/look', body: undefined }]);
	});

	it('Try on my screen shows the sheet here and saves nothing', async () => {
		const calls = serve(hers, echo);
		render(LookForm, { user: donna, onclose: () => {} });
		await button('Try on my screen').click();
		expect(root.getAttribute('data-look')).toBe('album');
		expect(root.getAttribute('data-theme')).toBe('light');
		expect(look.trial?.who).toEqual({ id: 2, name: 'Donna' });
		expect(look.saved).toEqual(mine);
		expect(calls.filter((c) => c.method === 'PUT')).toEqual([]);
	});

	it('while trying, each change shows at once', async () => {
		serve(hers, echo);
		render(LookForm, { user: donna, onclose: () => {} });
		await button('Try on my screen').click();
		await form().getByRole('combobox', { name: 'Theme', exact: true }).selectOptions('safelight');
		expect(root.getAttribute('data-look')).toBeNull();
		await form().getByRole('checkbox', { name: 'Accent colour: the theme’s own' }).click();
		expect(root.style.getPropertyValue('--acc-h')).toBe('72');
	});

	it('Stop trying puts my own look back', async () => {
		serve(hers, echo);
		render(LookForm, { user: donna, onclose: () => {} });
		await button('Try on my screen').click();
		await button('Stop trying').click();
		expect(look.trial).toBeNull();
		expect(root.getAttribute('data-look')).toBeNull();
		expect(root.style.getPropertyValue('--acc-h')).toBe('120');
		await expect.element(button('Try on my screen')).toBeVisible();
	});

	it('Save for … sends the whole sheet for that account, ends the trial and closes', async () => {
		const calls = serve(hers, echo);
		const onclose = vi.fn();
		render(LookForm, { user: donna, onclose });
		await form().getByRole('combobox', { name: 'Photo size', exact: true }).selectOptions('large');
		await form().getByRole('checkbox', { name: 'Words under the dock icons' }).click();
		await button('Try on my screen').click();
		await button('Save for Donna').click();

		await vi.waitFor(() => expect(onclose).toHaveBeenCalledOnce());
		expect(calls.at(-1)).toEqual({
			method: 'PUT',
			url: '/api/admin/accounts/2/look',
			body: { ...hers, thumbSize: 'large', dockLabels: false }
		});
		expect(look.trial).toBeNull();
		expect(look.saved).toEqual(mine); // her look, not mine
		expect(root.style.getPropertyValue('--acc-h')).toBe('120');
		expect(notice.text).toBe(
			'Saved the look for Donna. Their app shows it the next time it opens.'
		);
	});

	it('saving my own look shows it here at once', async () => {
		serve(mine, echo);
		render(LookForm, { user: admin, onclose: () => {} });
		const mineForm = page.getByRole('dialog', { name: 'Look for C' });
		await mineForm.getByRole('combobox', { name: 'Theme', exact: true }).selectOptions('album');
		await mineForm.getByRole('button', { name: 'Save for C' }).click();
		await vi.waitFor(() => expect(look.saved.theme).toBe('album'));
		expect(root.getAttribute('data-look')).toBe('album');
	});

	it('Reset look puts every field back to its default, saved only by Save', async () => {
		const calls = serve(hers, echo);
		render(LookForm, { user: donna, onclose: () => {} });
		await expect
			.element(form().getByRole('combobox', { name: 'Theme', exact: true }))
			.toHaveValue('album');
		await button('Reset look').click();
		await expect
			.element(form().getByRole('combobox', { name: 'Theme', exact: true }))
			.toHaveValue('safelight');
		await expect
			.element(form().getByRole('combobox', { name: 'Mode', exact: true }))
			.toHaveValue('dark');
		expect(calls.filter((c) => c.method === 'PUT')).toEqual([]);
		await button('Save for Donna').click();
		await vi.waitFor(() => expect(calls.at(-1)?.body).toEqual(DEFAULT_LOOK));
	});

	it('a dial taken from the theme is sent as a number, and given back as null', async () => {
		const calls = serve(hers, echo);
		render(LookForm, { user: donna, onclose: () => {} });
		const own = form().getByRole('checkbox', { name: 'Corners: the theme’s own' });
		await own.click();
		await expect.element(form().getByRole('slider', { name: 'Corners' })).toBeEnabled();
		await form().getByRole('slider', { name: 'Corners' }).fill('4');
		await own.click();
		await form().getByRole('checkbox', { name: 'Gap between photos: the theme’s own' }).click();
		await button('Save for Donna').click();
		await vi.waitFor(() =>
			expect(calls.at(-1)?.body).toMatchObject({ corners: null, photoGap: 3, accentHue: null })
		);
	});

	it('Collections rows can be hidden and moved, never all hidden', async () => {
		const calls = serve(hers, echo);
		render(LookForm, { user: donna, onclose: () => {} });
		await form().getByRole('checkbox', { name: 'Places' }).click();
		await form().getByRole('button', { name: 'Move Albums up' }).click();
		await form().getByRole('checkbox', { name: 'People' }).click();
		await expect.element(form().getByRole('checkbox', { name: 'Albums' })).toBeDisabled();
		await button('Save for Donna').click();
		await vi.waitFor(() =>
			expect(calls.at(-1)?.body).toMatchObject({ collectionsRows: ['albums'] })
		);
	});

	it('Home: whether the dock shows it, and which page the app opens on', async () => {
		const calls = serve(hers, echo); // hers opens on Library
		render(LookForm, { user: donna, onclose: () => {} });
		const opens = form().getByRole('combobox', { name: 'Opens on', exact: true });
		const shown = form().getByRole('checkbox', { name: 'Show Home' });
		await expect.element(opens).toHaveValue('library');
		await expect.element(shown).toBeChecked();
		await opens.selectOptions('today');
		await button('Save for Donna').click();
		await vi.waitFor(() =>
			expect(calls.at(-1)?.body).toMatchObject({ showToday: true, startPage: 'today' })
		);
	});

	it('without Home the app opens on Library, and that is not a choice', async () => {
		const calls = serve(parseLook({}), echo);
		render(LookForm, { user: donna, onclose: () => {} });
		const opens = form().getByRole('combobox', { name: 'Opens on', exact: true });
		await expect.element(opens).toHaveValue('today');
		await form().getByRole('checkbox', { name: 'Show Home' }).click();
		await expect.element(opens).toBeDisabled();
		await expect.element(opens).toHaveValue('library');
		await button('Save for Donna').click();
		await vi.waitFor(() =>
			expect(calls.at(-1)?.body).toMatchObject({ showToday: false, startPage: 'library' })
		);
	});

	it('a refused save says why and keeps the form open', async () => {
		serve(hers, () => ({ status: 422, json: { detail: "unknown look field 'css'" } }));
		const onclose = vi.fn();
		render(LookForm, { user: donna, onclose });
		await button('Save for Donna').click();
		// in the form itself: a toast would sit behind the dialog
		await expect.element(form().getByRole('alert')).toHaveTextContent("Unknown look field 'css'");
		expect(onclose).not.toHaveBeenCalled();
		await expect.element(button('Save for Donna')).toBeEnabled();
	});

	it('reopening the form while trying picks the trial up, without asking the server', async () => {
		const tried = parseLook({ theme: 'album', accentHue: 300 });
		look.try(tried, { id: 2, name: 'Donna' });
		const calls = serve(hers, echo);
		render(LookForm, { user: donna, onclose: () => {} });
		await expect.element(form().getByRole('slider', { name: 'Accent hue' })).toHaveValue('300');
		await expect.element(button('Stop trying')).toBeVisible();
		expect(calls).toEqual([]);
	});

	it('says so when the look cannot be fetched', async () => {
		vi.stubGlobal('fetch', async () => {
			throw new TypeError('Failed to fetch');
		});
		const onclose = vi.fn();
		render(LookForm, { user: donna, onclose });
		await vi.waitFor(() => expect(notice.text).toMatch(/could not be reached/));
		expect(onclose).toHaveBeenCalledOnce();
	});

	it('a fetch that fails after the form was closed closes nothing and says nothing', async () => {
		let fail!: (reason: unknown) => void;
		const asked = vi.fn(() => new Promise<Response>((_, reject) => (fail = reject)));
		vi.stubGlobal('fetch', asked);
		const onclose = vi.fn(); // the page's: it would close whichever Look form is open now
		const first = render(LookForm, { user: donna, onclose });
		await vi.waitFor(() => expect(asked).toHaveBeenCalledOnce());
		await first.unmount();

		fail(new TypeError('Failed to fetch'));
		await new Promise((done) => setTimeout(done, 50));

		expect(onclose).not.toHaveBeenCalled();
		expect(notice.text).toBe('');
	});

	it('a save that lands after the form was closed is told, but closes nothing', async () => {
		let answer!: (response: Response) => void;
		vi.stubGlobal('fetch', async (_: RequestInfo | URL, init?: RequestInit) =>
			init?.method === 'PUT'
				? new Promise<Response>((resolve) => (answer = resolve))
				: Response.json(hers)
		);
		const onclose = vi.fn();
		const first = render(LookForm, { user: donna, onclose });
		await button('Save for Donna').click();
		await vi.waitFor(() => expect(answer).toBeDefined());
		await first.unmount();

		answer(Response.json(hers));

		await vi.waitFor(() => expect(notice.text).toMatch(/^Saved the look for Donna/));
		expect(onclose).not.toHaveBeenCalled();
	});

	it('a dial left to the theme stands where that theme has it, and starts there', async () => {
		const calls = serve(hers, echo); // Album, light
		render(LookForm, { user: donna, onclose: () => {} });
		const slider = (name: string) => form().getByRole('slider', { name });
		await expect.element(slider('Accent hue')).toHaveValue('275');
		await expect.element(slider('Corners')).toHaveValue('3');
		await expect.element(slider('Gap between photos')).toHaveValue('3');

		await form().getByRole('combobox', { name: 'Mode', exact: true }).selectOptions('dark');
		await expect.element(slider('Accent hue')).toHaveValue('281');
		await form().getByRole('checkbox', { name: 'Accent colour: the theme’s own' }).click();
		await form().getByRole('checkbox', { name: 'Corners: the theme’s own' }).click();
		await button('Save for Donna').click();
		await vi.waitFor(() =>
			expect(calls.at(-1)?.body).toMatchObject({ theme: 'album', accentHue: 281, corners: 3 })
		);
	});

	it('the theme’s own values follow the theme chosen in the form', async () => {
		serve(hers, echo);
		render(LookForm, { user: donna, onclose: () => {} });
		await form().getByRole('combobox', { name: 'Theme', exact: true }).selectOptions('safelight');
		await expect.element(form().getByRole('slider', { name: 'Accent hue' })).toHaveValue('72');
		await expect.element(form().getByRole('slider', { name: 'Corners' })).toHaveValue('12');
	});
});

describe('LookTrial', () => {
	it('shows nothing until a look is being tried, then whose it is and Stop trying', async () => {
		render(LookTrial);
		await expect.element(page.getByText(/Trying a look/)).not.toBeInTheDocument();
		look.try(hers, { id: 2, name: 'Donna' });
		await expect
			.element(page.getByRole('status'))
			.toHaveTextContent('Trying a look for Donna. Nothing is saved yet.');
		await page.getByRole('button', { name: 'Stop trying' }).click();
		expect(look.trial).toBeNull();
		await expect.element(page.getByText(/Trying a look/)).not.toBeInTheDocument();
	});
});
