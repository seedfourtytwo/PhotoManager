import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ApiError, createApi, type Api } from '../src/lib/api/index.ts';
import { createMockApi } from './app.ts';
import { makeState } from './data.ts';

let server: Server;
let base: string;
let clock = 1_000_000;

/** fetch with a one-cookie jar, like a browser tab. */
function browser() {
	let cookie = '';
	const fetcher: typeof fetch = async (input, init) => {
		const headers = new Headers(init?.headers);
		if (cookie) headers.set('cookie', cookie);
		const response = await fetch(input, { ...init, headers });
		const set = response.headers.get('set-cookie');
		if (set) cookie = set.split(';')[0];
		return response;
	};
	return createApi({ base, fetch: fetcher });
}

async function start(users: 'none' | 'seed') {
	const mock = createMockApi(makeState({ users }), { now: () => clock });
	server = createServer((req, res) => void mock.handle(req, res));
	await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
	base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
}

async function signedIn(username = 'admin', pin = '1234'): Promise<Api> {
	const api = browser();
	await api.login({ username, pin });
	return api;
}

afterEach(() => new Promise<void>((resolve) => server.close(() => resolve())));

describe('first run', () => {
	beforeEach(() => start('none'));

	it('asks for an admin, creates one with a session, then refuses a second setup', async () => {
		const api = browser();
		expect(await api.setupState()).toEqual({ needs_admin: true });
		const user = await api.setup({ username: 'c', display_name: 'C', pin: '1234' });
		expect(user.role).toBe('admin');
		expect((await api.me()).username).toBe('c');
		await expect(
			api.setup({ username: 'x', display_name: 'X', pin: '1234' })
		).rejects.toMatchObject({ status: 409 });
	});

	it('rejects PINs that are not 4 digits', async () => {
		await expect(
			browser().setup({ username: 'c', display_name: 'C', pin: '12345' })
		).rejects.toMatchObject({ status: 422 });
	});
});

describe('with seeded users', () => {
	beforeEach(() => start('seed'));

	it('needs a session for everything but health, setup and login', async () => {
		const anon = browser();
		await expect(anon.health()).resolves.toMatchObject({ status: 'ok' });
		const error = await anon.assets({}).catch((e: unknown) => e);
		expect(error).toBeInstanceOf(ApiError);
		expect((error as ApiError).status).toBe(401);
	});

	it('lists the active accounts for the login screen, without a session', async () => {
		const admin = await signedIn();
		const guest = (await admin.users()).find((u) => u.username === 'guest')!;
		await admin.updateUser(guest.id, { disabled: true });
		expect(await browser().loginAccounts()).toEqual([
			{ username: 'admin', display_name: 'C' },
			{ username: 'partner', display_name: 'Partner' }
		]);
	});

	it('rate-limits login after 10 failures', async () => {
		const api = browser();
		for (let i = 0; i < 10; i++)
			await expect(api.login({ username: 'admin', pin: '0000' })).rejects.toMatchObject({
				status: 401
			});
		await expect(api.login({ username: 'admin', pin: '1234' })).rejects.toMatchObject({
			status: 429
		});
	});

	it('lets an admin unlock a rate-limited account', async () => {
		const api = browser();
		for (let i = 0; i < 10; i++)
			await api.login({ username: 'partner', pin: '0000' }).catch(() => undefined);
		const blocked = { username: 'partner', pin: '2345' };
		await expect(api.login(blocked)).rejects.toMatchObject({ status: 429 });
		const admin = await signedIn();
		const partner = (await admin.users()).find((u) => u.username === 'partner')!;
		const member = await signedIn('guest', '3456');
		await expect(member.unlockUser(partner.id)).rejects.toMatchObject({ status: 403 });
		await admin.unlockUser(partner.id);
		await expect(api.login(blocked)).resolves.toMatchObject({ username: 'partner' });
		await expect(admin.unlockUser(999)).rejects.toMatchObject({ status: 404 });
	});

	const MINUTE = 60_000;
	const PARTNER = { username: 'partner', pin: '2345' };

	/** Wrong PINs for partner, waiting out the 15-minute block whenever it comes. */
	async function guessWrong(times: number) {
		const api = browser();
		for (let i = 0; i < times; i++) {
			const refused = await api.login({ ...PARTNER, pin: '0000' }).catch((e: ApiError) => e.status);
			if (refused !== 429) continue;
			clock += 15 * MINUTE;
			await expect(api.login({ ...PARTNER, pin: '0000' })).rejects.toMatchObject({ status: 401 });
		}
	}

	const lockedFlags = async (admin: Api) =>
		Object.fromEntries((await admin.users()).map((u) => [u.username, u.locked]));

	it('counts wrong PINs per account, from any browser, and says how long to wait', async () => {
		for (let i = 0; i < 10; i++)
			await expect(browser().login({ ...PARTNER, pin: '0000' })).rejects.toMatchObject({
				status: 401
			});
		clock += 9.5 * MINUTE;
		await expect(browser().login({ username: 'Partner', pin: '2345' })).rejects.toMatchObject({
			status: 429,
			message:
				'Too many wrong PINs; wait 6 minutes and try again, or ask an admin to unlock this account'
		});
		await expect(signedIn()).resolves.toBeTruthy(); // another account is not held up
		const admin = await signedIn();
		expect((await lockedFlags(admin)).partner).toBe(true); // the wait shows as locked to admins
		clock += 5.5 * MINUTE;
		expect((await lockedFlags(admin)).partner).toBe(false);
		const partner = await browser().login(PARTNER);
		expect(partner).not.toHaveProperty('locked'); // told to admins only
	});

	it('does not count tries at a user name nobody has', async () => {
		for (let i = 0; i < 12; i++)
			await expect(browser().login({ username: 'nobody', pin: '0000' })).rejects.toMatchObject({
				status: 401
			});
	});

	it('locks an account after 30 wrong PINs, whatever PIN comes next, until an admin unlocks it', async () => {
		const admin = await signedIn();
		await guessWrong(29);
		expect(await lockedFlags(admin)).toEqual({ admin: false, partner: false, guest: false });
		await guessWrong(1);
		expect(await lockedFlags(admin)).toEqual({ admin: false, partner: true, guest: false });
		clock += 400 * 24 * 60 * MINUTE; // no window ends this
		await expect(browser().login(PARTNER)).rejects.toMatchObject({
			status: 423,
			message:
				"This account is locked after too many wrong PINs; ask an admin to unlock it, or set a new PIN on the server with 'just set-pin'"
		});
		expect(await browser().loginAccounts()).toContainEqual({
			username: 'partner',
			display_name: 'Partner'
		}); // names only: the open list says nothing about locks
		const guest = await signedIn('guest', '3456');
		const partner = (await admin.users()).find((u) => u.username === 'partner')!;
		await expect(guest.unlockUser(partner.id)).rejects.toMatchObject({ status: 403 });
		await admin.unlockUser(partner.id);
		expect((await lockedFlags(admin)).partner).toBe(false);
		await expect(browser().login(PARTNER)).resolves.toMatchObject({ username: 'partner' });
	});

	it('starts the count again after a good sign-in', async () => {
		await guessWrong(29);
		clock += 15 * MINUTE;
		await expect(browser().login(PARTNER)).resolves.toBeTruthy();
		await guessWrong(29);
		clock += 15 * MINUTE;
		await expect(browser().login(PARTNER)).resolves.toMatchObject({ username: 'partner' });
	});

	it('lifts the lock when an admin sets a new PIN, not for other changes', async () => {
		const admin = await signedIn();
		await guessWrong(30);
		const partner = (await admin.users()).find((u) => u.username === 'partner')!;
		expect(await admin.updateUser(partner.id, { display_name: 'P' })).toMatchObject({
			locked: true
		});
		expect(await admin.updateUser(partner.id, { pin: '9999' })).toMatchObject({ locked: false });
		await expect(browser().login({ ...PARTNER, pin: '9999' })).resolves.toBeTruthy();
	});

	it('counts wrong current PINs in Settings like wrong PINs at sign-in', async () => {
		const partner = await signedIn('partner', '2345');
		for (let i = 0; i < 10; i++)
			await expect(
				partner.changePin({ current_pin: '0000', new_pin: '5678' })
			).rejects.toMatchObject({ status: 400 });
		await expect(partner.changePin({ current_pin: '2345', new_pin: '5678' })).rejects.toMatchObject(
			{ status: 429 }
		);
		await expect(browser().login(PARTNER)).rejects.toMatchObject({ status: 429 });
		await guessWrong(20);
		await expect(partner.changePin({ current_pin: '2345', new_pin: '5678' })).rejects.toMatchObject(
			{ status: 423 }
		);
		expect(await partner.me()).toMatchObject({ username: 'partner' }); // the open session goes on
	});

	it('can start with a locked account (for the E2E suite)', async () => {
		const reset = await fetch(`${base}/__mock/reset`, {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ locked: 'guest' })
		});
		expect(reset.status).toBe(204);
		await expect(browser().login({ username: 'guest', pin: '3456' })).rejects.toMatchObject({
			status: 423
		});
		expect(await lockedFlags(await signedIn())).toEqual({
			admin: false,
			partner: false,
			guest: true
		});
	});

	it('logs out', async () => {
		const api = await signedIn();
		await api.logout();
		await expect(api.me()).rejects.toMatchObject({ status: 401 });
	});

	it('pages the timeline newest first with cursors', async () => {
		const api = await signedIn();
		const first = await api.assets({}, null, 100);
		expect(first.items).toHaveLength(100);
		const second = await api.assets({}, first.next_cursor, 500);
		const all = [...first.items, ...second.items];
		expect(second.next_cursor).toBeNull();
		const dates = all.map((a) => a.taken_at);
		expect([...dates].sort().reverse()).toEqual(dates);
		expect(new Set(all.map((a) => a.id)).size).toBe(all.length);
	});

	it('filters by year and place, and facets agree with the list', async () => {
		const api = await signedIn();
		const facets = await api.facets({});
		const year = facets.years[0];
		const page = await api.assets({ year: year.year }, null, 500);
		expect(page.items).toHaveLength(year.count);
		const paris = await api.assets({ place: 'paris' }, null, 500);
		expect(paris.items.every((a) => a.place?.city === 'Paris')).toBe(true);
		expect(facets.total).toBeGreaterThan(250);
	});

	it('hides hidden photos unless asked for them', async () => {
		const api = await signedIn();
		const hidden = await api.assets({ hidden: true }, null, 500);
		expect(hidden.items.length).toBeGreaterThan(0);
		const normal = await api.assets({}, null, 500);
		expect(normal.items.some((a) => a.id === hidden.items[0].id)).toBe(false);
	});

	it('limits what a member sees by source access', async () => {
		const admin = await signedIn();
		const guest = await signedIn('guest', '3456');
		const all = (await admin.facets({})).total;
		const seen = (await guest.facets({})).total;
		expect(seen).toBeLessThan(all);
		await expect(guest.users()).rejects.toMatchObject({ status: 403 });
	});

	it('fixes dates by shift and marks them manual', async () => {
		const api = await signedIn();
		const [a] = (await api.assets({}, null, 1)).items;
		await api.changeDates({ ids: [a.id], shift_minutes: -60 });
		const detail = await api.asset(a.id);
		expect(detail.date_source).toBe('manual');
		expect(Date.parse(`${a.taken_at}Z`) - Date.parse(`${detail.taken_at}Z`)).toBe(3_600_000);
	});

	it('saves and reverts an edit recipe, bumping the thumb version', async () => {
		const api = await signedIn();
		const [a] = (await api.assets({}, null, 1)).items;
		const recipe = {
			rotate: 90 as const,
			flip_horizontal: false,
			flip_vertical: false,
			crop: null,
			straighten: 0
		};
		await api.saveRecipe(a.id, recipe);
		const edited = await api.asset(a.id);
		expect(edited.edited).toBe(true);
		expect(edited.thumb?.url).not.toBe(a.thumb?.url);
		expect([edited.width, edited.height]).toEqual([a.height, a.width]);
		await api.revertRecipe(a.id);
		expect((await api.recipe(a.id)).rotate).toBe(0);
	});

	it('creates, fills, reorders and shares albums', async () => {
		const api = await signedIn();
		const ids = (await api.assets({}, null, 3)).items.map((a) => a.id);
		const album = await api.createAlbum({ title: 'Test', asset_ids: ids });
		expect(album.count).toBe(3);
		await api.reorderAlbum(album.id, [...ids].reverse());
		expect((await api.album(album.id)).items.map((a) => a.id)).toEqual([...ids].reverse());
		await api.updateAlbum(album.id, { cover_asset_id: ids[1] });
		expect((await api.album(album.id)).cover?.url).toContain(`/${ids[1]}/`);
		await api.setAlbumMembers(album.id, [{ user_id: 2, role: 'viewer' }]);
		expect(await api.albumMembers(album.id)).toEqual([{ user_id: 2, role: 'viewer' }]);
		await api.removeFromAlbum(album.id, [ids[0]]);
		expect((await api.album(album.id)).count).toBe(2);
	});

	it('estimates and streams a ZIP download', async () => {
		const api = await signedIn();
		const ids = (await api.assets({}, null, 2)).items.map((a) => a.id);
		const request = {
			ids,
			format: 'original' as const,
			quality: 90,
			max_edge: null,
			strip_location: false,
			strip_all_metadata: false,
			naming: 'date' as const,
			folders: 'year' as const
		};
		const estimate = await api.estimateDownload(request);
		expect(estimate.count).toBe(2);
		expect(estimate.bytes).toBeGreaterThan(0);
	});

	it('moves photos to the trash, restores them, and lets an admin empty it', async () => {
		const api = await signedIn();
		const ids = (await api.assets({}, null, 2)).items.map((a) => a.id);
		await api.trashAssets(ids);
		expect((await api.trash()).map((t) => t.id).sort()).toEqual([...ids].sort());
		await expect(api.asset(ids[0])).rejects.toMatchObject({ status: 404 });
		await api.restore([ids[0]]);
		expect((await api.emptyTrash()).purged).toBe(1);
		expect(await api.trash()).toEqual([]);
	});

	it('adds a source, scans it as a job, and reports every outcome', async () => {
		const api = await signedIn();
		const source = await api.addSource({ label: 'Scans', path: '/home/c/Scans' });
		expect(await api.sourceAccess(source.id)).toEqual({ everyone: 'download', users: [] });
		const queued = await api.scanSource(source.id);
		expect((await api.stats()).jobs.queued).toBeGreaterThan(0);
		clock += 5000;
		const jobs = await api.jobs();
		expect(jobs.find((j) => j.id === queued.job_id)?.status).toBe('done');
		const [run] = await api.imports(source.id);
		const report = await api.importReport(run.id);
		expect(report.items.map((i) => i.outcome).sort()).toEqual(
			[
				'duplicate',
				'failed',
				'imported',
				'imported',
				'imported',
				'imported',
				'imported',
				'imported',
				'skipped'
			].sort()
		);
		expect(report.items.find((i) => i.outcome === 'failed')?.reason).toMatch(/corrupt/);
		await expect(api.addSource({ label: 'X', path: '/missing' })).rejects.toThrow(/not found/);
	});

	it('lets an admin choose how often a folder checks itself again', async () => {
		const api = await signedIn();
		const [phone] = await api.sources();
		expect([phone.recheck, phone.next_check_at]).toEqual(['off', null]);
		const [run] = await api.imports(phone.id);
		const day = 24 * 3600 * 1000;

		const daily = await api.updateSource(phone.id, { recheck: 'daily' });
		expect(daily.recheck).toBe('daily');
		expect(Date.parse(daily.next_check_at!)).toBe(Date.parse(run.started_at) + day);
		expect((await api.sources())[0].next_check_at).toBe(daily.next_check_at);

		const weekly = await api.updateSource(phone.id, { recheck: 'weekly' });
		expect(Date.parse(weekly.next_check_at!)).toBe(Date.parse(run.started_at) + 7 * day);
		const disabled = await api.updateSource(phone.id, { enabled: false });
		expect([disabled.recheck, disabled.next_check_at]).toEqual(['weekly', null]);

		const added = await api.addSource({ label: 'Scans', path: '/home/c/Scans' });
		expect(added.recheck).toBe('off');
		const hourly = await api.updateSource(added.id, { recheck: 'hourly' });
		expect(Date.parse(hourly.next_check_at!)).toBe(clock); // never checked: due now

		// @ts-expect-error only the four settings exist
		await expect(api.updateSource(phone.id, { recheck: 'monthly' })).rejects.toMatchObject({
			status: 422
		});
		const guest = await signedIn('guest', '3456');
		await expect(api.updateSource(phone.id, { recheck: 'off' })).resolves.toBeTruthy();
		await expect(guest.updateSource(phone.id, { recheck: 'daily' })).rejects.toMatchObject({
			status: 403
		});
	});

	it('manages users and keeps at least one admin', async () => {
		const api = await signedIn();
		const user = await api.createUser({
			username: 'kid',
			display_name: 'Kid',
			pin: '1234',
			role: 'guest'
		});
		expect((await api.updateUser(user.id, { disabled: true })).disabled).toBe(true);
		await expect(api.updateUser(1, { role: 'member' })).rejects.toMatchObject({ status: 409 });
	});

	it('retries failed jobs', async () => {
		const api = await signedIn();
		const [failed] = await api.jobs('failed');
		expect(failed.error).toMatch(/libvips/);
		await api.retryJob(failed.id);
		expect(await api.jobs('failed')).toEqual([]);
	});
});

describe('contract v1.1 in the mock', () => {
	beforeEach(() => start('seed'));

	it('lists a user directory for members, not for guests', async () => {
		const members = await (await signedIn()).userDirectory();
		expect(members.length).toBeGreaterThan(1);
		expect(Object.keys(members[0]).sort()).toEqual(['display_name', 'id']);
	});

	it('stores uploaded photos in a private inbox and refuses other files', async () => {
		const api = await signedIn();
		const form = new FormData();
		form.append('file', new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2])]), 'a.jpg');
		form.append('file', new Blob(['hello']), 'notes.txt');
		const before = (await api.facets({})).total;
		const response = await fetch(`${api.base}/api/upload`, {
			method: 'POST',
			body: form,
			headers: { cookie: await sessionCookie() }
		});
		expect(response.status).toBe(200);
		const body = await response.json();
		expect(body.files.map((f: { outcome: string }) => f.outcome)).toEqual(['stored', 'rejected']);
		expect((await api.facets({})).total).toBe(before + 1);
		expect((await api.sources()).some((s) => s.kind === 'inbox')).toBe(true);
	});
});

/** A fresh admin session cookie, for raw requests the typed client doesn't make. */
async function sessionCookie(): Promise<string> {
	const response = await fetch(`${base}/api/auth/login`, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ username: 'admin', pin: '1234' })
	});
	return (response.headers.get('set-cookie') ?? '').split(';')[0];
}

describe('the mock answers like the server (routes/sources.py, imports.py, system.py)', () => {
	beforeEach(() => start('seed'));

	it('refuses a relative or missing folder with 422, and a folder added twice with 409', async () => {
		const api = await signedIn();
		await expect(api.addSource({ label: 'Rel', path: 'Pictures' })).rejects.toMatchObject({
			status: 422
		});
		await expect(api.addSource({ label: 'Gone', path: '/home/c/missing' })).rejects.toMatchObject({
			status: 422,
			message: expect.stringMatching(/folder not found/i)
		});
		await api.addSource({ label: 'Scans', path: '/home/c/Scans' });
		await expect(
			api.addSource({ label: 'Scans again', path: '/home/c/Scans/' })
		).rejects.toMatchObject({
			status: 409,
			message: expect.stringMatching(/already a source/i)
		});
	});

	it('lists only the sources a viewer may see, counting only the photos they can see', async () => {
		const all = await (await signedIn()).sources();
		expect(all.map((s) => s.id)).toEqual(expect.arrayContaining([1, 2, 3]));
		// Source 3 is shared with the partner alone.
		const partner = await (await signedIn('partner', '2345')).sources();
		expect(partner.map((s) => s.id)).toEqual(expect.arrayContaining([1, 2, 3]));
		const guest = await (await signedIn('guest', '3456')).sources();
		expect(guest.map((s) => s.id)).toEqual([1, 2]);
		expect(guest.every((s) => s.path === null)).toBe(true);
		for (const source of guest)
			expect(source.asset_count).toBeLessThanOrEqual(
				all.find((s) => s.id === source.id)!.asset_count
			);
	});

	it('keeps jobs, import runs, reports and source access for admins', async () => {
		const admin = await signedIn();
		const [run] = await admin.imports();
		for (const who of [await signedIn('partner', '2345'), await signedIn('guest', '3456')]) {
			await expect(who.jobs()).rejects.toMatchObject({ status: 403 });
			await expect(who.imports()).rejects.toMatchObject({ status: 403 });
			await expect(who.importReport(run.id)).rejects.toMatchObject({ status: 403 });
			await expect(who.sourceAccess(1)).rejects.toMatchObject({ status: 403 });
		}
		await expect(admin.jobs()).resolves.toBeInstanceOf(Array);
		await expect(admin.importReport(run.id)).resolves.toMatchObject({ id: run.id });
		await expect(admin.sourceAccess(1)).resolves.toMatchObject({ everyone: 'download' });
	});
});
