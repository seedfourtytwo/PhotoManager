import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import ApiStatus from './ApiStatus.svelte';

describe('ApiStatus', () => {
	it('shows the server version when the API answers', async () => {
		render(ApiStatus, { load: async () => ({ status: 'ok', version: '0.0.1' }) });
		await expect.element(page.getByText('Library server ok · v0.0.1')).toBeInTheDocument();
	});

	it('explains what to do when the API is down', async () => {
		render(ApiStatus, { load: async () => Promise.reject(new Error('offline')) });
		await expect.element(page.getByText(/not reachable/)).toBeInTheDocument();
	});
});
