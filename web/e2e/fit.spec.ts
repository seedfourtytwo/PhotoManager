/**
 * What must fit at the design table's sizes: from the narrowest phone up, with the look's text
 * dial at 1 and at its end, and in the laptop's side column (DESIGN_PRINCIPLES §5: "nothing
 * wraps to a second toolbar line", "dials at their ends").
 */
import type { Locator, Page } from '@playwright/test';
import { expect, isPhone, loupe, loupeAction, resetMock, signIn, test } from './helpers.ts';

const TARGET = 44;
const SIZES = [
	{ width: 390, scale: 1 },
	{ width: 390, scale: 1.25 },
	{ width: 320, scale: 1 },
	{ width: 320, scale: 1.25 }
];

/** A phone of this width whose look has this text size (set as the look sets it: on the root). */
async function resize(page: Page, width: number, scale: number) {
	await page.setViewportSize({ width, height: 800 });
	await page.evaluate(
		(value) => document.documentElement.style.setProperty('--text-scale', value),
		String(scale)
	);
}

const box = async (part: Locator) => (await part.boundingBox())!;

/** Every one of `parts` lies between the screen's left and right edges. */
async function onScreen(parts: Locator, width: number) {
	for (const part of await parts.all()) {
		const { x, width: w } = await box(part);
		expect(x).toBeGreaterThanOrEqual(0);
		expect(x + w).toBeLessThanOrEqual(width + 0.5);
	}
}

/** The page is as wide as the screen: nothing pushes it sideways (and the dock with it). */
const sideways = (page: Page, width: number) =>
	page.evaluate((w) => document.documentElement.scrollWidth - w, width);

test.beforeEach(async () => {
	await resetMock();
});

for (const { width, scale } of SIZES) {
	const size = `${width} px, text ${scale}`;

	test(`${size}: the Library is as wide as the screen and the dock is whole`, async ({ page }) => {
		test.skip(!isPhone(page), 'the dock is the phone’s');
		await signIn(page);
		await expect(page.locator('.tile').first()).toBeVisible();
		await resize(page, width, scale);
		await expect.poll(() => sideways(page, width)).toBeLessThanOrEqual(0);
		const nav = page.getByRole('navigation', { name: 'Main' });
		await onScreen(nav.locator('ul a, a.search, .account button'), width);
	});

	test(`${size}: the photo bar holds its five actions apart, each a whole target`, async ({
		page
	}) => {
		test.skip(!isPhone(page), 'the narrow bar is the phone’s');
		await signIn(page);
		await page.locator('.tile').first().click();
		const bar = loupe(page).locator('.bar');
		const actions = bar.locator('.acts .action');
		await expect(actions).toHaveCount(5);
		await resize(page, width, scale);
		await expect(async () => {
			const glass = await box(bar);
			expect(glass.x).toBeGreaterThanOrEqual(0);
			expect(glass.x + glass.width).toBeLessThanOrEqual(width);
			let edge = glass.x;
			for (const [i, action] of (await actions.all()).entries()) {
				const { x, width: w, height } = await box(action);
				expect(w).toBeGreaterThanOrEqual(TARGET);
				expect(height).toBeGreaterThanOrEqual(TARGET);
				// Real room between two actions; at the largest text at least the finest gap.
				if (i > 0) expect(x - edge).toBeGreaterThanOrEqual(scale === 1 ? 8 : 2);
				else expect(x).toBeGreaterThanOrEqual(edge);
				edge = x + w;
			}
			expect(edge).toBeLessThanOrEqual(glass.x + glass.width);
		}).toPass({ timeout: 3000 });
	});
}

const CONTROLS = 'button, input, select, textarea, label';

test('320 px at the largest text: a form’s sheet and its controls stay on the screen', async ({
	page
}) => {
	test.skip(!isPhone(page), 'a dialog is a bottom sheet on a phone');
	await signIn(page, '/albums');
	await resize(page, 320, 1.25);
	await page.getByRole('button', { name: 'New album' }).click();
	const sheet = page.getByRole('dialog', { name: 'New album' });
	await expect(sheet).toBeVisible();
	await onScreen(sheet, 320);
	await onScreen(sheet.locator(CONTROLS), 320);
});

test('320 px at the largest text: the photo’s sheets and their controls stay on the screen', async ({
	page
}) => {
	test.skip(!isPhone(page), 'a dialog is a bottom sheet on a phone');
	const width = 320;
	await signIn(page);
	await page.locator('.tile').first().click();
	await expect(loupe(page)).toBeVisible();
	await resize(page, width, 1.25);
	for (const [action, name] of [
		['Download', /^Download/],
		['Album', /album/i],
		['Fix date', /date/i]
	] as const) {
		await loupeAction(page, action);
		const sheet = page.getByRole('dialog', { name });
		await expect(sheet).toBeVisible();
		await onScreen(sheet, width);
		await onScreen(sheet.locator(CONTROLS), width);
		await sheet.getByRole('button', { name: 'Cancel' }).click();
		await expect(sheet).toBeHidden();
	}
});

for (const width of [1440, 1024]) {
	test(`laptop ${width} px: the filter column shows its search hint and its dates whole`, async ({
		page
	}) => {
		test.skip(isPhone(page), 'the side column is the laptop’s');
		await page.setViewportSize({ width, height: 768 });
		await signIn(page);
		const panel = page.getByRole('complementary', { name: 'Filters' });
		await expect(panel).toBeVisible();

		// A field's own width when nothing holds it: what it needs to show all it has.
		const short = (field: Locator) =>
			field.evaluate((el) => {
				const free = el.cloneNode(true) as HTMLElement;
				free.style.cssText = 'position: absolute; visibility: hidden; width: auto';
				el.parentElement!.append(free);
				const needs = free.getBoundingClientRect().width;
				free.remove();
				return Math.ceil(needs - el.getBoundingClientRect().width);
			});
		expect(await short(panel.getByLabel('From'))).toBeLessThanOrEqual(0);
		expect(await short(panel.getByLabel('To'))).toBeLessThanOrEqual(0);

		// The hint is not a value, so the field does not measure it: it is measured here. The
		// whole field is its room, because an empty field keeps none for its clear button
		// (fields.css; tokens.spec.ts holds that rule, which a page cannot see).
		const hint = await panel.getByRole('searchbox').evaluate((el) => {
			const field = el as HTMLInputElement;
			const style = getComputedStyle(field);
			const pen = document.createElement('canvas').getContext('2d')!;
			pen.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
			const room =
				field.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
			return { text: pen.measureText(field.placeholder).width, room };
		});
		expect(hint.text).toBeLessThanOrEqual(hint.room);
	});
}
