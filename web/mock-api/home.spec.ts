/** GET /api/home in the mock (issue 54): the server's rules, on the mock library. */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { startMock, type Harness } from './harness.ts';

const NOON_14_OCTOBER_2026 = Date.UTC(2026, 9, 14, 12);
const HOUR = 3_600_000;

let h: Harness;
beforeEach(async () => {
	h = await startMock('seed');
	h.clock.now = NOON_14_OCTOBER_2026;
	// the library again, its latest photos imported over the week before the mock's clock
	await h.browser().raw('/__mock/reset', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: '{}'
	});
});
afterEach(() => h.close());

describe('GET /api/home in the mock', () => {
	it('answers memories and what is new in the contract shape', async () => {
		const home = await (await h.signedIn()).home();
		expect(home.memories.length).toBeGreaterThan(2);
		expect(home.memories.length).toBeLessThanOrEqual(8);
		for (const m of home.memories) {
			expect(m.count).toBeGreaterThanOrEqual(10);
			expect(m.key).toBe(`${m.from}_${m.to}`);
			expect(m.filter).toEqual({ from: m.from, to: m.to, guessed_date: false });
			expect(m.title).toMatch(/^([^,]+, )?[A-Z][a-z]+ (\d{4} )?((and|to) [A-Z][a-z]+ )?\d{4}$/);
		}
		const newest = home.memories.slice(0, 2).map((m) => m.to);
		expect(newest).toEqual([...newest].sort().reverse());
		expect(home.new).toMatchObject({ days: 7, count: 30 });
		expect(home.new.items).toHaveLength(12);
		expect(home.new.sources.reduce((n, s) => n + s.count, 0)).toBe(30);
	});

	it('lists exactly the photos each block counts through its filter', async () => {
		const api = await h.signedIn();
		const [photo] = (await api.assets({ year: 2019 }, null, 1)).items;
		await api.changeDates({ ids: [photo.id], set: '2019-10-14T09:00:00' });
		const home = await api.home();
		const day = home.on_this_day!;
		expect(day.exact).toBe(true);
		expect(day.day.slice(5)).toBe('10-14');
		expect(day.years_ago).toBe(2026 - Number(day.day.slice(0, 4)));
		for (const block of [day, ...home.memories]) {
			const listed = (await api.assets(block.filter, null, 500)).items.map((a) => a.id);
			expect(listed).toHaveLength(block.count);
			expect(listed).toContain(block.cover.id);
		}
	});

	it('stays the same all day and turns its memories the next', async () => {
		const api = await h.signedIn();
		const morning = await api.home();
		h.clock.now += 6 * HOUR;
		expect((await api.home()).memories).toEqual(morning.memories);
		h.clock.now += 24 * HOUR;
		const tomorrow = await api.home();
		expect(tomorrow.memories.slice(0, 2)).toEqual(morning.memories.slice(0, 2));
		expect(tomorrow.memories.slice(2)).not.toEqual(morning.memories.slice(2));
	});

	it('keeps to what the account may see', async () => {
		const guest = await h.signedIn('guest', '3456');
		const home = await guest.home();
		const seen = new Set((await guest.assets({}, null, 500)).items.map((a) => a.id));
		const shown = [...home.memories.map((m) => m.cover), ...home.new.items];
		expect(shown.every((a) => seen.has(a.id))).toBe(true);
		expect(home.new.sources.map((s) => s.label)).not.toContain('Partner');
	});

	it('needs a session', async () => {
		await expect(h.browser().home()).rejects.toMatchObject({ status: 401 });
	});
});
