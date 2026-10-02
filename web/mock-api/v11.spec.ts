/**
 * The v1.1 routes the web app uses (search, people, print, backups, devices, remote sources)
 * and the M2-integration rules, exercised through the typed client against the mock.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { DownloadRequest } from '../src/lib/api/index.ts';
import { startMock, type Harness } from './harness.ts';

let h: Harness;
beforeEach(async () => (h = await startMock('seed')));
afterEach(() => h.close());

const zipRequest = (scope: object): DownloadRequest =>
	({
		...scope,
		format: 'original',
		quality: 90,
		max_edge: null,
		strip_location: false,
		strip_all_metadata: false,
		naming: 'original',
		folders: 'flat'
	}) as DownloadRequest;

describe('integration rules', () => {
	it('albums grant view only: an album viewer cannot download a photo it only sees there', async () => {
		const admin = await h.signedIn();
		const guest = await h.signedIn('guest', 'guest password');
		// Partner's source 3 is invisible to the guest; share an album holding one of its photos.
		const partnerOnly = h.mock.state.assets.find((a) => a.sources[0].source_id === 3)!;
		const album = await admin.createAlbum({ title: 'Shared', asset_ids: [partnerOnly.id] });
		await admin.setAlbumMembers(album.id, [{ user_id: 3, role: 'editor' }]);
		expect((await guest.asset(partnerOnly.id)).level).toBe('view');
		expect((await guest.estimateDownload(zipRequest({ album_id: album.id }))).count).toBe(0);
	});

	it('serves thumbnails and previews of trashed photos to whoever may see them', async () => {
		const api = await h.signedIn();
		const [a] = (await api.assets({}, null, 1)).items;
		await api.trashAssets([a.id]);
		const thumb = await api.raw(`/api/assets/${a.id}/thumb`);
		expect(thumb.status).toBe(200);
		expect((await api.raw(`/api/assets/${a.id}/preview`)).status).toBe(200);
		const guest = await h.signedIn('guest', 'guest password');
		const partnerOnly = h.mock.state.assets.find((x) => x.sources[0].source_id === 3)!;
		await api.trashAssets([partnerOnly.id]);
		expect((await guest.raw(`/api/assets/${partnerOnly.id}/thumb`)).status).toBe(404);
	});

	it('a scan of a folder that disappeared fails with a reason', async () => {
		const api = await h.signedIn();
		const source = await api.addSource({ label: 'Gone', path: '/media/usb-gone' });
		await api.scanSource(source.id);
		h.clock.now += 5000;
		await api.jobs();
		const [run] = await api.imports(source.id);
		expect(run.status).toBe('failed');
		expect(run.message).toMatch(/folder not found/);
	});

	it('names the ZIP after the album or the scope', async () => {
		const api = await h.signedIn();
		const form = (request: DownloadRequest) =>
			api.raw('/api/downloads', {
				method: 'POST',
				headers: { 'content-type': 'application/x-www-form-urlencoded' },
				body: new URLSearchParams({ request: JSON.stringify(request) }).toString()
			});
		const album = await form(zipRequest({ album_id: 1 }));
		expect(album.headers.get('content-disposition')).toContain('Summers at the house.zip');
		const year = await form(zipRequest({ filters: { year: 2019 } }));
		expect(year.headers.get('content-disposition')).toContain('photos-2019.zip');
	});

	it('answers errors as JSON {detail}, also for unknown routes', async () => {
		const api = await h.signedIn();
		const response = await api.raw('/api/nothing-here');
		expect(response.status).toBe(404);
		expect(await response.json()).toEqual({ detail: expect.any(String) });
	});
});

describe('search and people', () => {
	it('falls back to word search and says why when models are missing', async () => {
		const api = await h.signedIn();
		expect((await api.mlStatus()).models_installed).toBe(false);
		const result = await api.search('carnac');
		expect(result.mode).toBe('text');
		expect(result.detail).toMatch(/just models/);
		expect(result.items.length).toBeGreaterThan(0);
		await expect(api.similar(result.items[0].id)).rejects.toMatchObject({ status: 503 });
	});

	it('ranks by meaning when models are installed, and finds similar photos', async () => {
		h.mock.state.ml.installed = true;
		const api = await h.signedIn();
		const result = await api.search('beach at sunset');
		expect(result.mode).toBe('semantic');
		expect(result.items[0].score).toBeGreaterThan(0);
		const similar = await api.similar(result.items[0].id, 10);
		expect(similar).toHaveLength(10);
		expect(similar.every((s) => s.id !== result.items[0].id)).toBe(true);
	});

	it('lists people, renames, merges and pages a person’s photos', async () => {
		const api = await h.signedIn();
		const people = await api.people();
		expect(people.length).toBeGreaterThan(2);
		const [a, b] = people;
		expect((await api.renamePerson(a.id, 'Léa')).name).toBe('Léa');
		const merged = await api.mergePeople(a.id, [b.id]);
		expect(merged.face_count).toBe(a.face_count + b.face_count);
		expect((await api.people()).some((p) => p.id === b.id)).toBe(false);
		const page = await api.personAssets(a.id, null, 5);
		expect(page.items).toHaveLength(5);
		expect(page.next_cursor).not.toBeNull();
		const guest = await h.signedIn('guest', 'guest password');
		await expect(guest.renamePerson(a.id, 'x')).rejects.toMatchObject({ status: 403 });
	});
});

describe('print', () => {
	it('offers trims and themes, plans pages with resolution issues, previews and prints', async () => {
		const api = await h.signedIn();
		const options = await api.printOptions();
		expect(options.trims.map((t) => t.id)).toContain('a4-landscape');
		const request = { trim: 'a4-landscape', theme: 'quiet', cover: true, crop_marks: false };
		const plan = await api.printPlan(1, request);
		expect(plan.page_count).toBe(plan.pages.length + 1);
		expect(plan.issues.length).toBeGreaterThan(0);
		const preview = await api.raw(api.printPreviewUrl(1, 1, request));
		expect(preview.status).toBe(200);
		const pdf = await api.printPdf(1, { ...request, allow_low_resolution: true });
		expect(pdf.filename).toBe('Summers at the house.pdf');
		expect(pdf.blob.size).toBeGreaterThan(0);
		await expect(api.printPdf(1, request)).rejects.toMatchObject({ status: 422 });
	});
});

describe('backups, devices and remote sources', () => {
	it('adds a backup target, runs it, and lists the runs', async () => {
		const api = await h.signedIn();
		const [existing] = await api.backups();
		expect(existing.needs_attention).toBe(true);
		const target = await api.addBackup({
			label: 'USB disk',
			repository: '/media/usb/restic',
			password_file: '/home/c/.restic-pass',
			schedule: 'daily 02:30'
		});
		expect(target.enabled).toBe(true);
		const queued = await api.runBackup(target.id);
		expect(queued.target_id).toBe(target.id);
		h.clock.now += 5000;
		const runs = await api.backupRuns(target.id);
		expect(runs[0].status).toBe('succeeded');
		await api.restoreTest(target.id);
		expect((await api.setBackupEnabled(target.id, false)).enabled).toBe(false);
		const member = await h.signedIn('partner', 'battery staple');
		await expect(member.backups()).rejects.toMatchObject({ status: 403 });
	});

	it('creates a device token once, lists and revokes it', async () => {
		const api = await h.signedIn();
		const created = await api.createDevice({ name: 'Léa’s iPhone', platform: 'ios' });
		expect(created.token).toMatch(/^pa_dev_/);
		const listed = await api.devices();
		expect(listed.map((d) => d.name)).toContain('Léa’s iPhone');
		expect(JSON.stringify(listed)).not.toContain(created.token);
		await api.revokeDevice(created.device.id);
		expect((await api.devices()).find((d) => d.id === created.device.id)?.revoked).toBe(true);
	});

	it('lists rclone remotes, adds a remote source and pulls it', async () => {
		const api = await h.signedIn();
		const { remotes } = await api.remotes();
		expect(remotes).toContain('gdrive');
		const source = await api.addRemoteSource({ label: 'Drive', remote: 'gdrive', path: 'Photos' });
		expect((await api.sources()).find((s) => s.id === source.id)?.kind).toBe('rclone');
		expect((await api.pullRemoteSource(source.id)).source_id).toBe(source.id);
		await expect(
			api.addRemoteSource({ label: 'X', remote: 'nope', path: '' })
		).rejects.toMatchObject({ status: 422 });
	});
});
