/** Suggested albums in the mock (v1.12): the server's rules, on the mock library. */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { startMock, type Harness } from './harness.ts';

let h: Harness;
beforeEach(async () => {
	h = await startMock('seed');
});
afterEach(() => h.close());

describe('suggested albums in the mock', () => {
	it('proposes a few events, newest first, named from facts', async () => {
		const found = await (await h.signedIn()).albumSuggestions();
		expect(found.length).toBeGreaterThan(0);
		expect(found.length).toBeLessThanOrEqual(6);
		for (const s of found) {
			expect(s.count).toBeGreaterThanOrEqual(8);
			expect(s.items.length).toBe(4);
			expect(s.from <= s.to).toBe(true);
			expect(s.title).toMatch(/^([^·]+ · )?(\d{1,2} )?[A-Z][a-z]+( \d{4})?( (and|to) [A-Z][a-z]+)? \d{4}$/);
		}
		const ends = found.map((s) => s.to);
		expect(ends).toEqual([...ends].sort().reverse());
	});

	it('makes the album only on Keep, and an answered suggestion does not come back', async () => {
		const api = await h.signedIn();
		const [first, second] = await api.albumSuggestions();
		const albums = (await api.albums()).length;

		await api.discardSuggestion(second.key);
		expect((await api.albums()).length).toBe(albums);
		const kept = await api.keepSuggestion(first.key);

		expect(kept).toMatchObject({ title: first.title, count: first.count, role: 'owner' });
		const keys = (await api.albumSuggestions()).map((s) => s.key);
		expect(keys).not.toContain(first.key);
		expect(keys).not.toContain(second.key);
		await expect(api.keepSuggestion(first.key)).rejects.toMatchObject({ status: 404 });
	});
});
