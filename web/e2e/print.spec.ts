/** Album → print: trim and theme, page previews, resolution warnings, the PDF. */
import { expect, expectAccessible, REAL_BACKEND, resetMock, signIn, test } from './helpers.ts';

test.beforeEach(async ({ page }) => {
	await resetMock();
	await signIn(page, '/albums/1');
});

test('print an album: choose size and theme, see every page, warnings, then the PDF', async ({
	page
}) => {
	await page.getByRole('link', { name: 'Print' }).click();
	await expect(page).toHaveURL(/\/albums\/1\/print$/);
	await expect(page.getByRole('heading', { name: /Print/ })).toBeVisible();
	const pages = page.getByRole('list', { name: 'Pages' }).getByRole('img');
	await expect(pages.first()).toBeVisible();
	const count = Number(
		(await page
			.getByText(/\d+ pages/)
			.first()
			.textContent())!.match(/(\d+) pages/)![1]
	);
	await expect(pages).toHaveCount(count);
	await expect(pages.first()).toHaveAttribute('alt', /Cover/);

	const plan = page.waitForRequest((r) => r.url().endsWith('/print/plan'));
	await page.getByRole('combobox', { name: 'Size' }).selectOption({ label: 'Square 20 cm' });
	expect((await plan).postDataJSON()).toMatchObject({ trim: 'square-20' });
	await page.getByRole('radio', { name: /Warm/ }).check();
	await expect(pages.first()).toHaveAttribute('src', /theme=warm/);
	await expectAccessible(page);

	const issues = page.getByRole('region', { name: 'Resolution' });
	if (REAL_BACKEND) return; // the synthetic server library may print sharply
	await expect(issues.getByText(/too small to print sharply|may look soft/).first()).toBeVisible();
	await page.getByRole('button', { name: 'Download PDF' }).click();
	await expect(page.getByRole('alert').filter({ hasText: /too small/ })).toBeVisible();
	await page.getByLabel(/Print anyway/).check();
	const download = page.waitForEvent('download');
	await page.getByRole('button', { name: 'Download PDF' }).click();
	expect((await download).suggestedFilename()).toBe('Summers at the house.pdf');
});
