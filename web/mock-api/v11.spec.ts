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
		const guest = await h.signedIn('guest', '3456');
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
		const guest = await h.signedIn('guest', '3456');
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
		const place = await form(zipRequest({ filters: { year: 2019, place: 'France' } }));
		expect(place.headers.get('content-disposition')).toBe(
			`attachment; filename="photos-2019-france.zip"; filename*=UTF-8''photos-2019-france.zip`
		);
		const all = await form(zipRequest({ filters: {} }));
		expect(all.headers.get('content-disposition')).toContain('photos-all.zip');
		const ids = await form(zipRequest({ ids: [1, 2, 2] }));
		expect(ids.headers.get('content-disposition')).toContain("filename*=UTF-8''photos-2.zip");
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
		const guest = await h.signedIn('guest', '3456');
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
	it("lists the server's folders for picking one, to admins only", async () => {
		const api = await h.signedIn();
		const home = await api.folders();
		expect(home).toMatchObject({ path: '/home/c', parent: '/home' });
		expect(home.folders.map((f) => f.name)).toEqual(['Documents', 'Pictures', 'Scans']);
		expect(home.roots.map((r) => r.label)).toEqual(['Home', 'Tiny stick', 'USB disk']);
		expect(home.source_problem).toContain('photo library itself');
		const pictures = await api.folders('/home/c/Pictures/');
		expect(pictures.path).toBe('/home/c/Pictures');
		expect(pictures.source_problem).toBeNull();
		await api.addSource({ label: 'Pics', path: pictures.path });
		expect((await api.folders(pictures.path)).source_problem).toBe('already added as “Pics”');
		expect((await api.folders('/')).parent).toBeNull();
		await expect(api.folders('/home/c/missing')).rejects.toMatchObject({ status: 422 });
		await expect(api.folders('Pictures')).rejects.toMatchObject({ status: 422 });
		const member = await h.signedIn('partner', '2345');
		await expect(member.folders()).rejects.toMatchObject({ status: 403 });
	});

	it('guided setup: checks the place, hands over the key, backs up and proves the restore', async () => {
		const api = await h.signedIn();
		const places = await api.backupPlaces();
		expect(places.disks.map((d) => d.label)).toEqual(['Tiny stick', 'USB disk']);
		expect(places.remotes).toEqual(['proton']);

		const small = await api.planBackup('/media/c/Tiny stick');
		expect(small.ok).toBe(false);
		expect(small.problem).toContain('36.4 GB missing');
		expect((await api.planBackup('/media/c/Gone')).problem).toContain('plugged in');
		expect((await api.planBackup('backups')).problem).toContain('absolute path');
		expect((await api.planBackup('/home/c/backups')).warnings[0]).toContain('same disk');
		expect((await api.planBackup('rclone:proton:')).repository).toBe(
			'rclone:proton:photo-assistant-backup'
		);
		await expect(
			api.setUpBackup({ label: 'Stick', place: '/media/c/Tiny stick' })
		).rejects.toMatchObject({ status: 422 });

		const { target, recovery } = await api.setUpBackup({
			label: 'USB',
			place: '/media/c/USB disk'
		});
		expect(target).toMatchObject({
			key_saved: false,
			needs_attention: true,
			schedule: 'daily 02:30'
		});
		expect(recovery.repository).toBe('/media/c/USB disk/photo-assistant-backup');
		expect(recovery.key.length).toBeGreaterThanOrEqual(40);
		expect(target.last_run?.status).toBe('running');
		await expect(
			api.setUpBackup({ label: 'usb', place: '/home/c/elsewhere' })
		).rejects.toMatchObject({ status: 409 });
		expect((await api.planBackup('/media/c/USB disk')).problem).toContain('already a backup');

		h.clock.now += 5000;
		const runs = await api.backupRuns(target.id);
		expect(runs.map((r) => [r.kind, r.status])).toEqual([
			['restore_test', 'succeeded'],
			['backup', 'succeeded']
		]);
		expect(await api.backupRecovery(target.id)).toEqual(recovery);
		const saved = await api.confirmBackupKey(target.id);
		expect(saved).toMatchObject({ key_saved: true, needs_attention: false });
		expect(saved.last_proven_at).toBeTruthy();
		const member = await h.signedIn('partner', '2345');
		await expect(member.backupPlaces()).rejects.toMatchObject({ status: 403 });
		await expect(member.backupRecovery(target.id)).rejects.toMatchObject({ status: 403 });
	});

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
		expect((await api.updateBackup(target.id, { enabled: false })).enabled).toBe(false);
		const changed = await api.updateBackup(target.id, {
			schedule: 'weekly sun 03:00',
			quiet_window: '22:00-06:00',
			retention: { weekly: 2 }
		});
		expect(changed).toMatchObject({
			schedule: 'weekly sun 03:00',
			quiet_window: '22:00-06:00',
			retention: { daily: 7, weekly: 2, monthly: 12 },
			enabled: false
		});
		expect((await api.updateBackup(target.id, { quiet_window: null })).quiet_window).toBeNull();
		await expect(api.updateBackup(target.id, { schedule: 'often' })).rejects.toMatchObject({
			status: 422
		});
		const member = await h.signedIn('partner', '2345');
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
