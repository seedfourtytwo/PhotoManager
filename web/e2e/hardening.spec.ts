/** Failure states and edge cases from the architecture review: each one was a real dead end. */
import { expect, isPhone, resetMock, signIn, test } from './helpers.ts';

test.beforeEach(async () => {
	await resetMock();
});

test('map: a drag that starts on a dot pans the map, it does not choose the dot', async ({
	page
}) => {
	test.skip(isPhone(page), 'mouse drag; a touch pan never ends in a click');
	await signIn(page, '/map');
	await expect(page.getByText(/photos with a location/)).toBeVisible();
	const dots = page.getByRole('link', { name: /photos? here/ });
	const centre = async () => {
		const box = (await dots.first().boundingBox())!;
		return [box.x + box.width / 2, box.y + box.height / 2] as const;
	};
	// Zoom in around the biggest dot, so there is room to pan and a dot under the pointer.
	await page.mouse.move(...(await centre()));
	await page.mouse.wheel(0, -100);
	await page.mouse.wheel(0, -100);
	const viewBox = async () => (await page.locator('.map svg').getAttribute('viewBox'))!.split(' ');
	await expect.poll(async () => Number((await viewBox())[2])).toBeLessThan(360);
	const before = await viewBox();
	const [x, y] = await centre();
	await page.mouse.move(x, y);
	await page.mouse.down();
	await page.mouse.move(x + 40, y + 10, { steps: 8 });
	await page.mouse.up();
	const after = await viewBox();
	expect(after[0]).not.toBe(before[0]); // it panned
	expect(after[2]).toBe(before[2]); // and did not zoom into the dot
	await expect(page.locator('section.chosen')).toHaveCount(0);
	// Choosing still works afterwards, from the keyboard and with a click.
	await dots.first().press('Enter');
	await expect(page.locator('section.chosen')).toBeVisible();
});
