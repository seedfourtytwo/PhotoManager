import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { DEFAULT_LOOK, parseLook } from '../src/lib/look/sheet.ts';
import { startMock, type Harness } from './harness.ts';

let mock: Harness;
beforeEach(async () => {
	mock = await startMock();
});
afterEach(() => mock.close());

const WARM = parseLook({ theme: 'album', mode: 'light', accentHue: 30, textScale: 1.15 });

describe('the look in the mock, as the backend serves it (contract v1.5)', () => {
	it('every account starts with the defaults', async () => {
		const partner = await mock.signedIn('partner', '2345');
		expect(await partner.myLook()).toEqual(DEFAULT_LOOK);
	});

	it('an account changes its mode and nothing else', async () => {
		const admin = await mock.signedIn();
		const partner = await mock.signedIn('partner', '2345');
		const guest = await mock.signedIn('guest', '3456');
		const partnerId = (await admin.users()).find((u) => u.username === 'partner')!.id;
		await admin.setAccountLook(partnerId, WARM);

		expect(await partner.setMyMode('system')).toEqual({ ...WARM, mode: 'system' });
		expect(await partner.myLook()).toEqual({ ...WARM, mode: 'system' });
		expect((await guest.setMyMode('light')).mode).toBe('light');
		expect(await admin.myLook()).toEqual(DEFAULT_LOOK);

		for (const body of [{ mode: 'light', accentHue: 200 }, { theme: 'album' }, {}, ['light']]) {
			const refused = await partner.raw('/api/me/look', {
				method: 'PUT',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify(body)
			});
			expect(refused.status).toBe(422);
		}
		await expect(partner.setMyMode('sepia' as 'dark')).rejects.toMatchObject({ status: 422 });
		expect(await partner.myLook()).toEqual({ ...WARM, mode: 'system' });
	});

	it('only an admin reads or sets another account’s look', async () => {
		const admin = await mock.signedIn();
		const partner = await mock.signedIn('partner', '2345');
		const partnerId = (await admin.users()).find((u) => u.username === 'partner')!.id;

		await expect(partner.accountLook(partnerId)).rejects.toMatchObject({ status: 403 });
		await expect(partner.setAccountLook(partnerId, WARM)).rejects.toMatchObject({ status: 403 });
		expect(await admin.setAccountLook(partnerId, WARM)).toEqual(WARM);
		expect(await admin.accountLook(partnerId)).toEqual(WARM);
		expect(await partner.myLook()).toEqual(WARM);
		await expect(admin.accountLook(999)).rejects.toMatchObject({ status: 404 });
	});

	it('rejects unknown fields, clamps numbers, and resets on an empty sheet', async () => {
		const admin = await mock.signedIn();
		const me = (await admin.me()).id;
		await expect(
			admin.setAccountLook(me, { ...WARM, css: 'x' } as typeof WARM)
		).rejects.toMatchObject({ status: 422, message: expect.stringContaining("'css'") });
		expect(await admin.setAccountLook(me, { accentHue: 720, textScale: 3 })).toMatchObject({
			accentHue: 360,
			textScale: 1.25
		});
		expect(await admin.setAccountLook(me, {})).toEqual(DEFAULT_LOOK);
	});

	it('a reset of the mock forgets every look', async () => {
		const admin = await mock.signedIn();
		await admin.setMyMode('light');
		const reset = await fetch(`${mock.base}/__mock/reset`, { method: 'POST' });
		expect(reset.status).toBe(204);
		expect(await (await mock.signedIn()).myLook()).toEqual(DEFAULT_LOOK);
	});
});
