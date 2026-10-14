import { test } from './helpers.ts';

/**
 * A patched answer (`page.route` + `route.fetch()`) can still be on its way when its test
 * ends: a page that polls asks again every second or so. Closing the page throws away what
 * was fetched, so the handler fails ("Response has been disposed"), and Playwright blames
 * whichever test runs at that moment. The second test here is that bystander.
 */
const HANDLER_MS = 1000;

test.describe.serial('a route handler that outlives its test', () => {
	test('is still reading its fetched answer when the test ends', async ({ page }) => {
		await page.route('**/api/health', async (route) => {
			const response = await route.fetch();
			await new Promise((r) => setTimeout(r, HANDLER_MS));
			await route.fulfill({ response, json: await response.json() });
		});
		await page.goto('/login');
		const asked = page.waitForRequest('**/api/health');
		await page.evaluate(() => void fetch('/api/health').catch(() => undefined));
		await asked;
	});

	test('does not fail the test that runs next', async ({ page }) => {
		await page.goto('/login');
		await page.waitForTimeout(HANDLER_MS * 1.5);
	});
});
