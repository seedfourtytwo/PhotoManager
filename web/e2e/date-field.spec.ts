/** The date field of Fix date and of the filters: paste anything, see day first and 24 hours. */
import type { Locator, Page } from '@playwright/test';
import {
	expect,
	expectAccessible,
	isPhone,
	loupeAction,
	resetMock,
	signIn,
	test
} from './helpers.ts';

test.beforeEach(async ({ page, context }) => {
	await resetMock();
	await signIn(page);
	await context.grantPermissions(['clipboard-read', 'clipboard-write']);
});

/** Copy `text` as if from anywhere, then paste it into the field with the keyboard. */
async function paste(page: Page, field: Locator, text: string) {
	await page.evaluate((copied) => navigator.clipboard.writeText(copied), text);
	await field.focus();
	await page.keyboard.press('ControlOrMeta+V');
}

async function openSetExactly(page: Page) {
	await page.locator('.tile').first().click();
	await loupeAction(page, 'Fix date');
	const dialog = page.getByRole('dialog', { name: 'Fix date' });
	await dialog.getByLabel('Set exactly').check();
	return { dialog, field: dialog.getByLabel('Date and time') };
}

test('fix date: a pasted camera date is tidied at once, previewed and sent', async ({ page }) => {
	const { dialog, field } = await openSetExactly(page);
	await expect(field).toHaveValue(/^\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}:\d{2}$/);
	await paste(page, field, '2001:02:03 04:05:06');
	await expect(field).toHaveValue('03/02/2001 04:05:06');
	await expect(dialog.getByRole('cell').last()).toHaveText('3 Feb 2001, 04:05');
	await expectAccessible(page);
	const post = page.waitForRequest((r) => r.url().endsWith('/api/assets/dates'));
	await dialog.getByRole('button', { name: 'Change date' }).click();
	expect((await post).postDataJSON()).toMatchObject({ set: '2001-02-03T04:05:06' });
});

test('fix date: a pasted day keeps the time, a pasted time keeps the day, AM/PM becomes 24-hour', async ({
	page
}) => {
	const { dialog, field } = await openSetExactly(page);
	await paste(page, field, '2001:02:03 04:05:06');
	await paste(page, field, '4 juillet 2019');
	await expect(field).toHaveValue('04/07/2019 04:05:06');
	await paste(page, field, '12:05 AM');
	await expect(field).toHaveValue('04/07/2019 00:05:00');
	await expect(dialog.getByRole('cell').last()).toHaveText('4 Jul 2019, 00:05');
});

test('fix date: a month-first date is converted, and the dialog says it read it that way', async ({
	page
}) => {
	const { dialog, field } = await openSetExactly(page);
	await paste(page, field, '7/25/2019 6:30 PM');
	await expect(field).toHaveValue('25/07/2019 18:30:00');
	await expect(dialog.getByText('Read as month first: 25 July 2019')).toBeVisible();
	await expect(dialog.getByRole('cell').last()).toHaveText('25 Jul 2019, 18:30');
});

test('fix date: text that is not a date is pasted as it is, refused in words, and cannot be sent', async ({
	page
}) => {
	const { dialog, field } = await openSetExactly(page);
	await field.fill('');
	await paste(page, field, '31/02/2019 10:00');
	await expect(field).toHaveValue('31/02/2019 10:00');
	await expect(dialog.getByRole('button', { name: 'Change date' })).toBeDisabled();
	await field.press('Enter');
	await expect(dialog.getByRole('alert')).toHaveText(
		"Can't read that as a date. Try 04/07/2019 18:30."
	);
	await expect(dialog.getByRole('table')).toHaveCount(0);
	await expectAccessible(page);
	// Typed right, it is tidied on leaving the field and can be sent.
	await field.fill('3.2.2001 4:05');
	await field.blur();
	await expect(field).toHaveValue('03/02/2001 04:05:00');
	await expect(dialog.getByRole('alert')).toHaveCount(0);
	await expect(dialog.getByRole('button', { name: 'Change date' })).toBeEnabled();
});

test('phone: the date field is 16 px and a finger tall, in Fix date and in the filters', async ({
	page
}) => {
	test.skip(!isPhone(page), 'iOS zooms into small fields; a laptop has a pointer');
	const size = (field: Locator) =>
		field.evaluate((el) => ({
			font: parseFloat(getComputedStyle(el).fontSize),
			height: el.getBoundingClientRect().height
		}));
	await page.getByRole('button', { name: 'Filter', exact: true }).click();
	const from = page.getByRole('complementary', { name: 'Filters' }).getByLabel('From');
	expect((await size(from)).font).toBeGreaterThanOrEqual(16);
	expect((await size(from)).height).toBeGreaterThanOrEqual(44);
	await page.getByRole('button', { name: 'Done' }).click();
	const { field } = await openSetExactly(page);
	expect((await size(field)).font).toBeGreaterThanOrEqual(16);
	expect((await size(field)).height).toBeGreaterThanOrEqual(44);
});

test('filters: a pasted date in any format filters by that day, shown day first', async ({
	page
}) => {
	if (isPhone(page)) await page.getByRole('button', { name: 'Filter', exact: true }).click();
	const panel = page.getByRole('complementary', { name: 'Filters' });
	await paste(page, panel.getByLabel('From'), 'IMG_20190704_183005.jpg');
	await expect(panel.getByLabel('From')).toHaveValue('04/07/2019');
	await expect(page).toHaveURL(/from=2019-07-04/);
	// Something that is not a date changes nothing and is said under the field.
	await panel.getByLabel('To', { exact: true }).fill('next week');
	await panel.getByLabel('To', { exact: true }).press('Enter');
	await expect(panel.getByRole('alert')).toHaveText("Can't read that as a date. Try 04/07/2019.");
	await expect(page).toHaveURL(/from=2019-07-04$/);
	// Emptied, a field clears its filter.
	await panel.getByLabel('From').fill('');
	await panel.getByLabel('From').press('Enter');
	await expect(page).not.toHaveURL(/from=/);
});
