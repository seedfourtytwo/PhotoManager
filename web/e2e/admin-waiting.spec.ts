import { expect, expectAccessible, resetMock, signIn, test } from './helpers.ts';

/**
 * A job that failed and waits for its next attempt is counted by the server (`jobs.waiting`)
 * and must be visible: on the Problems tile, and in its list with the time it is tried again. The answers are the real routes' shapes, filled in here.
 */
test('admin sees the jobs that wait for another try, and when', async ({ page }) => {
	await resetMock();
	const soon = new Date(Date.now() + 5 * 60_000).toISOString();
	await page.route('**/api/stats', async (route) => {
		const real = await (await route.fetch()).json();
		await route.fulfill({ json: { ...real, jobs: { ...real.jobs, waiting: 1 } } });
	});
	await page.route('**/api/jobs?status=waiting', (route) =>
		route.fulfill({
			json: [
				{
					id: 41,
					kind: 'scan_source',
					payload: { source_id: 2 },
					status: 'queued',
					attempts: 1,
					error: "SyncError: pulling from 'mega' failed: connection reset",
					run_after: soon
				}
			]
		})
	);
	await signIn(page, '/settings/overview');

	// Problems is a status tile that says it, and opens the list.
	const tile = page.getByRole('button', { name: /^Problems/ });
	await expect(tile).toContainText('1 waiting to be retried');
	await tile.click();
	const problems = page.getByRole('dialog', { name: 'Problems' });
	const row = problems.getByRole('listitem').filter({ hasText: 'scan_source' });
	await expect(row).toContainText('connection reset');
	await expect(row).toContainText(/retrying at .*\d{2}:\d{2}/);
	await expect(row.getByRole('button')).toHaveCount(0);
	await expect(problems.getByRole('button', { name: 'Retry' })).toHaveCount(1);
	await expectAccessible(page);
});
