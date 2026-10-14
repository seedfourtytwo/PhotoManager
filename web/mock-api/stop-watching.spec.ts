/** Stop watching a folder (v1.6) and pausing one, through the typed client against the mock. */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { startMock, type Harness } from './harness.ts';

let h: Harness;
beforeEach(async () => (h = await startMock('seed')));
afterEach(() => h.close());

const OLD_DISK = 2;
/** The photos in the folder that are not in the trash. */
const inFolder = (id: number) =>
	h.mock.state.assets.filter(
		(a) => a.trashed_at === null && a.sources.some((s) => s.source_id === id)
	);
/** Those of them that no other folder holds. */
const onlyIn = (id: number) =>
	inFolder(id).filter((a) => a.sources.every((s) => s.source_id === id));
/** One that anyone with access to the folder sees in the library. */
const plain = (id: number) => onlyIn(id).find((a) => a.held === null && a.private_owner === null)!;

/** Gives one photo found only on the old disk a second home on the phone folder; its id. */
function shareOne(): number {
	const shared = plain(OLD_DISK);
	shared.sources.push({ source_id: 1, relative_path: 'copy.jpg' });
	return shared.id;
}

describe('stop watching a folder', () => {
	it('previews how many photos are found only in that folder', async () => {
		const api = await h.signedIn();
		const before = onlyIn(OLD_DISK).length;
		shareOne();
		expect(await api.sourceRemoval(OLD_DISK)).toEqual({
			photos: inFolder(OLD_DISK).length,
			only_here: before - 1
		});
	});

	it('keep: the folder is no longer watched, and everyone still sees its photos', async () => {
		const api = await h.signedIn();
		const partner = await h.signedIn('partner', '2345');
		const only = plain(OLD_DISK).id;
		const level = (await partner.asset(only)).level;

		const removed = await api.removeSource(OLD_DISK, 'keep');

		expect(removed).toMatchObject({ trashed: 0, detached: true });
		const kept = (await api.sources()).find((s) => s.id === OLD_DISK)!;
		expect([kept.kind, kept.enabled, kept.path, kept.recheck]).toEqual([
			'kept',
			false,
			null,
			'off'
		]);
		expect((await partner.asset(only)).level).toBe(level);
		await expect(api.scanSource(OLD_DISK)).rejects.toMatchObject({ status: 422 });
		await expect(api.updateSource(OLD_DISK, { enabled: true })).rejects.toMatchObject({
			status: 422
		});
		expect((await api.scanAll()).map((q) => q.source_id)).not.toContain(OLD_DISK);
	});

	it('removing a kept folder for good leaves its only photos to admins', async () => {
		const api = await h.signedIn();
		const partner = await h.signedIn('partner', '2345');
		const shared = shareOne();
		const only = plain(OLD_DISK).id;
		await api.removeSource(OLD_DISK, 'keep');

		const removed = await api.removeSource(OLD_DISK, 'keep');

		expect(removed).toMatchObject({ trashed: 0, detached: false });
		expect((await api.sources()).map((s) => s.id)).not.toContain(OLD_DISK);
		expect((await api.asset(only)).id).toBe(only);
		await expect(partner.asset(only)).rejects.toMatchObject({ status: 404 });
		expect((await partner.asset(shared)).id).toBe(shared);
	});

	it('trash: only the photos found nowhere else go to the trash', async () => {
		const api = await h.signedIn();
		const shared = shareOne();
		const only = onlyIn(OLD_DISK).map((a) => a.id);
		const trashedBefore = (await api.trash()).map((a) => a.id);

		const removed = await api.removeSource(OLD_DISK, 'trash');

		expect(removed).toEqual({ only_here: only.length, trashed: only.length, detached: false });
		const trashed = (await api.trash()).map((a) => a.id);
		expect(trashed.filter((id) => !trashedBefore.includes(id)).sort()).toEqual(only.sort());
		expect((await api.asset(shared)).id).toBe(shared);
	});

	it('refuses members, unknown folders and a folder whose check is running', async () => {
		const api = await h.signedIn();
		const partner = await h.signedIn('partner', '2345');
		await expect(partner.removeSource(OLD_DISK, 'keep')).rejects.toMatchObject({ status: 403 });
		await expect(api.removeSource(99, 'keep')).rejects.toMatchObject({ status: 404 });
		await api.scanSource(OLD_DISK);
		h.clock.now += 1000; // queued 0.8 s, then running
		await expect(api.removeSource(OLD_DISK, 'keep')).rejects.toMatchObject({ status: 409 });
	});

	it('a check still waiting goes with the folder', async () => {
		const api = await h.signedIn();
		await api.scanSource(OLD_DISK);
		await api.removeSource(OLD_DISK, 'keep');
		const scans = h.mock.state.jobs.filter((j) => j.payload.source_id === OLD_DISK);
		expect(scans).toEqual([]);
	});
});

describe('pause checking', () => {
	it('keeps the folder’s photos visible, like the server', async () => {
		const partner = await h.signedIn('partner', '2345');
		const [photo] = inFolder(OLD_DISK);
		const api = await h.signedIn();
		await api.updateSource(OLD_DISK, { enabled: false });
		expect((await partner.asset(photo.id)).id).toBe(photo.id);
	});
});
