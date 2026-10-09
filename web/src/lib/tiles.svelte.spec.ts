import { afterEach, describe, expect, it } from 'vitest';
import { photoAt, tileOf } from './tiles';

/** A grid of tiles as PhotoGrid draws them, 50 px squares side by side at the top left. */
function grid(ids: number[]): HTMLElement {
	const root = document.createElement('div');
	root.style.cssText = 'position: fixed; left: 0; top: 0; display: flex;';
	for (const id of ids) {
		const tile = document.createElement('button');
		tile.className = 'tile';
		tile.dataset.id = String(id);
		tile.style.cssText = 'width: 50px; height: 50px; padding: 0; border: 0;';
		tile.append(document.createElement('span'));
		root.append(tile);
	}
	document.body.append(root);
	return root;
}

describe('tiles', () => {
	afterEach(() => document.body.replaceChildren());

	it('tileOf finds the tile of a photo on the page', () => {
		const root = grid([7, 8]);
		expect(tileOf(8)).toBe(root.children[1]);
	});

	it('tileOf is null for a photo that is not rendered', () => {
		grid([7, 8]);
		expect(tileOf(9)).toBeNull();
	});

	it('tileOf with a root looks inside that root only', () => {
		const first = grid([7]);
		const second = grid([8]);
		expect(tileOf(8, first)).toBeNull();
		expect(tileOf(8, second)).toBe(second.children[0]);
	});

	it('tileOf does not take something else carrying the same data-id for a tile', () => {
		const root = grid([7]);
		const other = document.createElement('div');
		other.dataset.id = '8';
		root.append(other);
		expect(tileOf(8)).toBeNull();
	});

	it('photoAt names the photo under a point, also when the point is on something inside the tile', () => {
		const root = grid([7, 8]);
		(root.children[1].firstElementChild as HTMLElement).style.cssText =
			'display: block; width: 50px; height: 50px;';
		expect(photoAt(25, 25)).toBe(7);
		expect(photoAt(75, 25)).toBe(8);
	});

	it('photoAt is null where there is no tile', () => {
		grid([7, 8]);
		expect(photoAt(150, 25)).toBeNull();
		expect(photoAt(25, 150)).toBeNull();
	});
});
