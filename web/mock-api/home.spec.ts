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

	it('answers a dozen photos to rediscover, older than 30 days, a favourite first', async () => {
		const api = await h.signedIn();
		const [loved] = (await api.assets({ year: 2019 }, null, 1)).items;
		await api.setState(loved.id, { favourite: true });
		const { rediscover } = await api.home();
		expect(rediscover).toHaveLength(12);
		const monthAgo = new Date(NOON_14_OCTOBER_2026 - 30 * 24 * HOUR).toISOString().slice(0, 10);
		expect(rediscover.every((a) => a.taken_at.slice(0, 10) < monthAgo)).toBe(true);
		expect(rediscover[0].favourite).toBe(true);
		const rest = rediscover.slice(1).map((a) => a.taken_at);
		expect(rest).toEqual([...rest].sort());
		// the mock library spans 2012 to 2026: one photo from each of twelve of its years
		expect(new Set(rediscover.map((a) => a.taken_at.slice(0, 4))).size).toBe(12);
	});

	it('answers each year with ten dated photos, newest first, as a whole year', async () => {
		const { years } = await (await h.signedIn()).home();
		expect(years.length).toBeGreaterThan(1);
		for (const y of years) {
			expect(y.count).toBeGreaterThanOrEqual(10);
			expect([y.from, y.to, y.key]).toEqual([
				`${y.title}-01-01`,
				`${y.title}-12-31`,
				`${y.title}-01-01_${y.title}-12-31`
			]);
		}
		const titles = years.map((y) => y.title);
		expect(titles).toEqual([...titles].sort().reverse());
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
		for (const block of [day, ...home.memories, ...home.years]) {
			const listed = (await api.assets(block.filter, null, 500)).items.map((a) => a.id);
			expect(listed).toHaveLength(block.count);
			expect(listed).toContain(block.cover.id);
		}
	});

	it('stays the same all day and turns its memories the next', async () => {
		const api = await h.signedIn();
		const morning = await api.home();
		h.clock.now += 6 * HOUR;
		const later = await api.home();
		expect([later.memories, later.rediscover, later.years]).toEqual([
			morning.memories,
			morning.rediscover,
			morning.years
		]);
		h.clock.now += 24 * HOUR;
		const tomorrow = await api.home();
		expect(tomorrow.memories.slice(0, 2)).toEqual(morning.memories.slice(0, 2));
		expect(tomorrow.memories.slice(2)).not.toEqual(morning.memories.slice(2));
		expect(tomorrow.rediscover.map((a) => a.id)).not.toEqual(morning.rediscover.map((a) => a.id));
	});

	it('keeps to what the account may see', async () => {
		const guest = await h.signedIn('guest', '3456');
		const home = await guest.home();
		const seen = new Set((await guest.assets({}, null, 500)).items.map((a) => a.id));
		const covers = [...home.memories, ...home.years].map((m) => m.cover);
		const shown = [...covers, ...home.rediscover, ...home.new.items];
		expect(shown.every((a) => seen.has(a.id))).toBe(true);
		expect(home.new.sources.map((s) => s.label)).not.toContain('Partner');
	});

	it('needs a session', async () => {
		await expect(h.browser().home()).rejects.toMatchObject({ status: 401 });
	});
});
