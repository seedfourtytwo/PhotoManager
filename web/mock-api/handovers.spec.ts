import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ApiError, type Api } from '../src/lib/api/index.ts';
import { startMock, type Harness } from './harness.ts';

let mock: Harness;
let admin: Api & { raw: typeof fetch };

const post = (path: string, body: unknown) =>
	fetch(`${mock.base}${path}`, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(body)
	});
const status = (call: Promise<unknown>) =>
	call.then(
		() => 200,
		(error: unknown) => (error instanceof ApiError ? error.status : -1)
	);
const tokenOf = (url: string) => url.split('#')[1];
const send = (ids: number[], more: object = {}) =>
	admin.createHandover({
		ids,
		via: 'home',
		remove_details: true,
		unencrypted_ok: true,
		...more
	});

beforeEach(async () => {
	mock = await startMock();
	admin = await mock.signedIn();
});
afterEach(() => mock.close());

describe('send to a device, switched off (as the product ships)', () => {
	it('answers 404 on every route, with or without a session', async () => {
		expect(await status(admin.handoverOptions())).toBe(404);
		expect(await status(admin.handovers())).toBe(404);
		expect(await status(send([1]))).toBe(404);
		expect((await post('/api/handovers/look', { token: 'x' })).status).toBe(404);
		expect((await post('/api/handovers/collect', { token: 'x' })).status).toBe(404);
	});
});

describe('send to a device, switched on', () => {
	beforeEach(() => {
		mock.mock.state.sendToDevice.enabled = true;
	});

	it('offers the home address, unencrypted, and an https one when there is one', async () => {
		const options = await admin.handoverOptions();
		expect(options.addresses.map((a) => [a.via, a.encrypted])).toEqual([['home', false]]);
		expect(options).toMatchObject({ unencrypted_allowed: true, remove_details: true, minutes: 10 });
		mock.mock.state.sendToDevice.https = true;
		const both = (await admin.handoverOptions()).addresses;
		expect(both.map((a) => [a.via, a.encrypted])).toEqual([
			['here', true],
			['home', false]
		]);
		expect(both[0].origin).toMatch(/^https:/);
	});

	it('makes a link once the unencrypted warning is confirmed, and shows its token only then', async () => {
		expect(await status(send([1, 2], { unencrypted_ok: false }))).toBe(409);
		const made = await send([1, 2, 2]);
		expect(made).toMatchObject({
			state: 'waiting',
			count: 2,
			encrypted: false,
			details_removed: true
		});
		expect(made.url).toMatch(/^http:\/\/127\.0\.0\.1:\d+\/receive\.html#[\w-]{43}$/);
		const listed = await admin.handovers();
		expect(JSON.stringify(listed)).not.toContain(tokenOf(made.url));
		expect(listed[0].sent_by.display_name).toBe('C');
	});

	it('refuses a guest, an unknown photo, no photo and a switched-off unencrypted link', async () => {
		const guest = await mock.signedIn('guest', '3456');
		expect(await status(guest.handoverOptions())).toBe(403);
		expect(
			await status(guest.createHandover({ ids: [1], via: 'home', remove_details: true }))
		).toBe(403);
		expect(await status(send([999_999]))).toBe(404);
		expect(await status(send([]))).toBe(422);
		expect(await status(send([1], { via: 'here' }))).toBe(422);
		mock.mock.state.sendToDevice.unencrypted = false;
		expect(await status(send([1]))).toBe(403);
	});

	it('lets a device without a session look, then collect once', async () => {
		const made = await send([1, 2]);
		const token = tokenOf(made.url);
		const looked = await post('/api/handovers/look', { token });
		expect(await looked.json()).toMatchObject({
			count: 2,
			sent_by: 'C',
			encrypted: false,
			details_removed: true
		});
		expect(looked.headers.get('cache-control')).toBe('no-store');
		expect((await admin.handover(made.id)).state).toBe('waiting');

		const got = await post('/api/handovers/collect', { token });
		expect(got.status).toBe(200);
		expect(got.headers.get('content-type')).toBe('application/zip');
		expect(got.headers.get('content-disposition')).toContain('photos-2.zip');
		expect(got.headers.get('referrer-policy')).toBe('no-referrer');
		const after = await admin.handover(made.id);
		expect(after.state).toBe('redeemed');
		expect(after.redeemed_at).not.toBeNull();

		for (const path of ['/api/handovers/look', '/api/handovers/collect']) {
			const again = await post(path, { token });
			expect(again.status).toBe(404);
			expect((await again.json()).detail).toContain('does not work any more');
		}
	});

	it('sends one photo as a file, under a neutral name when details are removed', async () => {
		const plain = await send([1]);
		const got = await post('/api/handovers/collect', { token: tokenOf(plain.url) });
		expect(got.headers.get('content-disposition')).toContain('filename="photo.svg"');
		const kept = await send([1], { remove_details: false });
		const named = await post('/api/handovers/collect', { token: tokenOf(kept.url) });
		expect(named.headers.get('content-disposition')).not.toContain('filename="photo.svg"');
	});

	it('gives one answer for a wrong, cancelled and expired token', async () => {
		const cancelled = await send([1]);
		await admin.cancelHandover(cancelled.id);
		expect(await status(admin.cancelHandover(cancelled.id))).toBe(409);
		const expired = await send([1]);
		mock.clock.now += 10 * 60_000; // exactly at its expiry time
		expect((await admin.handover(expired.id)).state).toBe('expired');
		const answers = new Set<string>();
		for (const token of ['never-issued', tokenOf(cancelled.url), tokenOf(expired.url)]) {
			const answer = await post('/api/handovers/look', { token });
			answers.add(`${answer.status} ${await answer.text()}`);
		}
		expect(answers.size).toBe(1);
	});

	it('shows a member their own links and an admin everyone’s', async () => {
		const partner = await mock.signedIn('partner', '2345');
		const theirs = await partner.createHandover({
			ids: [1],
			via: 'home',
			remove_details: true,
			unencrypted_ok: true
		});
		const mine = await send([2]);
		expect((await partner.handovers()).map((h) => h.id)).toEqual([theirs.id]);
		expect((await admin.handovers()).map((h) => h.id)).toEqual([mine.id, theirs.id]);
		expect(await status(partner.handover(mine.id))).toBe(404);
		expect(await status(partner.cancelHandover(mine.id))).toBe(404);
		await admin.cancelHandover(theirs.id);
		expect((await partner.handover(theirs.id)).state).toBe('cancelled');
	});
});
