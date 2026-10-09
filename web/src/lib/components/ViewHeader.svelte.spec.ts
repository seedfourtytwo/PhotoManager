import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import ViewHeader from './ViewHeader.svelte';

const meta = () => page.getByRole('paragraph');

describe('ViewHeader', () => {
	it('counts photos in words: one photo, many photos', async () => {
		const view = render(ViewHeader, { view: 'grid', query: '', total: 1, described: '' });
		await expect.element(meta()).toHaveTextContent(/^1 photo$/);
		await view.rerender({ total: 1204 });
		await expect.element(meta()).toHaveTextContent(/^1,204 photos$/);
	});

	it('says it is counting, never an old number, until the total is known', async () => {
		render(ViewHeader, { view: 'grid', query: '?year=2019', total: null, described: '2019' });
		await expect.element(meta()).toHaveTextContent(/^Counting…\s·\s2019$/);
	});
});
