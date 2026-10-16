/**
 * People: leaving someone out of the list (a stranger in the background) and back in, and
 * choosing the round portrait.
 */
import type { Page } from '@playwright/test';
import {
	expect,
	expectAccessible,
	GUEST,
	REAL_BACKEND,
	resetMock,
	signIn,
	test,
	toast
} from './helpers.ts';

test.beforeEach(async () => {
	test.skip(REAL_BACKEND, 'faces need the ML models, which the E2E server does not have');
	await resetMock();
});

const someone = /^Someone/;

/** The person's tools wait behind the round ⋯ in the page head. */
async function personTool(page: Page, name: string) {
	await page.getByRole('button', { name: 'More', exact: true }).click();
	await page.getByRole('button', { name, exact: true }).click();
}

test('a hidden person leaves People, and Undo brings them back', async ({ page }) => {
	await signIn(page, '/people');
	const strangers = page.getByRole('link', { name: someone });
	const before = await strangers.count();
	await strangers.first().click();
	await personTool(page, 'Hide person');

	await expect(page).toHaveURL(/\/people$/);
	await expect(toast(page)).toContainText('hidden from People');
	await expect(strangers).toHaveCount(before - 1);
	await toast(page).getByRole('button', { name: 'Undo' }).click();
	await expect(strangers).toHaveCount(before);
	await expect(page.getByText(/^Hidden/)).toHaveCount(0);
});

test('hidden people wait in their own list and can be shown again', async ({ page }) => {
	await signIn(page, '/people');
	const strangers = page.getByRole('link', { name: someone });
	const before = await strangers.count();
	await strangers.first().click();
	await expect(page).toHaveURL(/\/people\/\d+$/);
	const person = page.url();
	await personTool(page, 'Hide person');
	await expect(strangers).toHaveCount(before - 1);

	// Their own page still opens, says so, and offers the way back.
	await page.goto(person);
	await expect(page.getByText('Hidden from People')).toBeVisible();
	await page.getByRole('button', { name: 'More', exact: true }).click();
	await expect(page.getByRole('button', { name: 'Show again' })).toBeVisible();
	await expect(page.getByRole('button', { name: 'Hide person' })).toHaveCount(0);
	await page.keyboard.press('Escape');

	await page.goto('/people');
	await page.getByRole('button', { name: /^Hidden people/ }).click();
	await page.getByRole('button', { name: 'Show again' }).click();
	await expect(strangers).toHaveCount(before);
	await expect(page.getByText(/^Hidden/)).toHaveCount(0);
});

test('a guest cannot hide anyone and is not shown the hidden list', async ({ page }) => {
	await signIn(page, '/people');
	await page.getByRole('link', { name: someone }).first().click();
	await personTool(page, 'Hide person');
	await expect(toast(page)).toContainText('hidden from People');
	await page.context().clearCookies();

	await signIn(page, '/people', GUEST);
	await expect(page.getByRole('heading', { name: 'People' })).toBeVisible();
	await expect(page.getByText(/^Hidden/)).toHaveCount(0);
	await page.getByRole('main').locator('a[href^="/people/"]').first().click();
	await expect(page.locator('.tile').first()).toBeVisible();
	// a guest has no tools for a person: no ⋯ at all
	await expect(page.getByRole('button', { name: 'More', exact: true })).toHaveCount(0);
	await expect(page.getByRole('button', { name: 'Hide person' })).toHaveCount(0);
});

// --- the portrait ------------------------------------------------------------------------------

type Circle = { face_id: number; asset_id: number; cx: number; cy: number; size: number };

/** A named person's page, and the round picture in its heading. */
async function openSomeoneNamed(page: Page, who = undefined as typeof GUEST | undefined) {
	await signIn(page, '/people', who);
	await page.getByRole('link', { name: /^Léa/ }).click();
	await expect(page).toHaveURL(/\/people\/\d+$/);
	const portrait = page.locator('header .face img');
	await expect(portrait).toBeVisible();
	return portrait;
}

test('change a portrait: pick another photo, zoom, save; the page shows the new picture', async ({
	page
}) => {
	const portrait = await openSomeoneNamed(page);
	const before = await portrait.getAttribute('src');
	const faces = page.waitForResponse((r) => /\/api\/people\/\d+\/faces/.test(r.url()));
	await personTool(page, 'Change portrait');
	const dialog = page.getByRole('dialog', { name: 'Change portrait' });
	const offered = (await (await faces).json()) as Circle[];
	expect(offered.length).toBeGreaterThan(1);
	await expect(dialog.getByRole('button', { name: 'Photo 1', exact: true })).toHaveAttribute(
		'aria-pressed',
		'true'
	);

	await dialog.getByRole('button', { name: 'Photo 2', exact: true }).click();
	await expect(dialog.getByRole('button', { name: 'Save' })).toBeEnabled();
	const stage = dialog.getByRole('group', { name: /^Portrait/ });
	await stage.focus();
	await page.keyboard.press('+');
	await page.keyboard.press('+');
	await page.keyboard.press('ArrowRight');

	const saved = page.waitForRequest((r) => r.method() === 'PUT' && r.url().endsWith('/portrait'));
	await dialog.getByRole('button', { name: 'Save' }).click();
	const sent = (await saved).postDataJSON() as Circle;
	expect(sent.face_id).toBe(offered[1].face_id);
	expect(sent.size).toBeLessThan(offered[1].size);
	expect(sent.cx).toBeGreaterThan(offered[1].cx);
	expect(sent.cy).toBeCloseTo(offered[1].cy);

	await expect(dialog).toHaveCount(0);
	await expect(portrait).not.toHaveAttribute('src', before!);
	expect(await portrait.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true); // prettier-ignore
	// and on People, whose card shows the photo the portrait now comes from
	await page.goto('/people');
	await expect(page.getByRole('link', { name: /^Léa/ }).locator('img')).toHaveAttribute(
		'src',
		new RegExp(`/api/assets/${offered[1].asset_id}/preview`)
	);
});

test('the portrait itself opens the dialog, and a drag moves the photo under the window', async ({
	page
}) => {
	await openSomeoneNamed(page);
	await page.getByRole('button', { name: 'Change portrait of Léa' }).click();
	const dialog = page.getByRole('dialog', { name: 'Change portrait' });
	await expect(dialog.getByRole('button', { name: 'Save' })).toBeEnabled();
	// Axe must not measure contrast while the dialog is still fading in.
	await expect(dialog).toHaveCSS('opacity', '1');
	await expectAccessible(page);
	const stage = dialog.getByRole('group', { name: /^Portrait/ });
	const photo = stage.locator('img');
	const start = await photo.boundingBox();
	const box = (await stage.boundingBox())!;
	// zoom in first, so there is room to move in both directions
	await stage.focus();
	for (let i = 0; i < 4; i++) await page.keyboard.press('+');
	const zoomed = await photo.boundingBox();
	expect(zoomed!.width).toBeGreaterThan(start!.width);

	const from = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
	await stage.dispatchEvent('pointerdown', { pointerId: 1, button: 0, isPrimary: true, clientX: from.x, clientY: from.y }); // prettier-ignore
	await stage.dispatchEvent('pointermove', { pointerId: 1, isPrimary: true, clientX: from.x + 30, clientY: from.y + 20 }); // prettier-ignore
	await stage.dispatchEvent('pointerup', { pointerId: 1, isPrimary: true, clientX: from.x + 30, clientY: from.y + 20 }); // prettier-ignore
	const moved = await photo.boundingBox();
	expect(moved!.x).toBeGreaterThan(zoomed!.x);
	expect(moved!.y).toBeGreaterThan(zoomed!.y);
	// the circle never leaves the photo: the photo always covers the whole stage
	expect(moved!.x).toBeLessThanOrEqual(box.x + 0.5);
	expect(moved!.y).toBeLessThanOrEqual(box.y + 0.5);
	expect(moved!.x + moved!.width).toBeGreaterThanOrEqual(box.x + box.width - 0.5);
	expect(moved!.y + moved!.height).toBeGreaterThanOrEqual(box.y + box.height - 0.5);
});

test('“Use automatic” goes back to the automatic portrait', async ({ page }) => {
	const portrait = await openSomeoneNamed(page);
	const automatic = await portrait.getAttribute('src');
	await personTool(page, 'Change portrait');
	const dialog = page.getByRole('dialog', { name: 'Change portrait' });
	await expect(dialog.getByRole('button', { name: 'Use automatic' })).toBeDisabled();
	await expect(dialog.getByRole('button', { name: 'Save' })).toBeEnabled();
	await dialog.getByRole('group', { name: /^Portrait/ }).focus();
	await page.keyboard.press('+');
	await dialog.getByRole('button', { name: 'Save' }).click();
	await expect(portrait).not.toHaveAttribute('src', automatic!);

	await personTool(page, 'Change portrait');
	const cleared = page.waitForRequest(
		(r) => r.method() === 'DELETE' && r.url().endsWith('/portrait')
	);
	await dialog.getByRole('button', { name: 'Use automatic' }).click();
	await cleared;
	await expect(dialog).toHaveCount(0);
	await expect(portrait).toHaveAttribute('src', automatic!);
});

test('a guest sees the portrait and cannot change it', async ({ page }) => {
	const portrait = await openSomeoneNamed(page, GUEST);
	await expect(portrait).toHaveAttribute('src', /\/portrait\?v=/);
	await expect(page.getByRole('button', { name: /Change portrait/ })).toHaveCount(0);
});

test('a person plays as a story, and opens in the Library with Who answered', async ({ page }) => {
	await signIn(page, '/people');
	const first = page
		.getByRole('main')
		.locator('a[href^="/people/"]')
		.filter({ hasNotText: /^Someone/ })
		.first();
	const name = await first.locator('.name').innerText();
	await first.click();
	await page.getByRole('button', { name: 'Play' }).click();
	const story = page
		.getByRole('dialog')
		.filter({ has: page.getByRole('button', { name: 'Pause' }) });
	await expect(story).toBeVisible();
	await page.keyboard.press('Escape');
	await expect(story).toBeHidden();

	await page.getByRole('link', { name: 'Show in Library' }).click();
	await expect(page).toHaveURL(/\/\?person_id=\d+$/);
	const who = page.getByRole('group', { name: 'Filters' }).getByRole('button').first();
	await expect(who).toHaveText(name.trim());
	await expect(page.getByRole('img', { name: /^Photo/ }).first()).toBeVisible();
});
