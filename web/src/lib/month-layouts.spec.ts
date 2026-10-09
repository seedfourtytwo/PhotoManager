import { describe, expect, it } from 'vitest';
import { monthLayouts } from './month-layouts';
import { makeAsset } from './testing/fixtures';
import { aspect, groupByMonth, justify } from './timeline';

const december = [1, 2, 3].map((id) => makeAsset(id, '2020-12-01T00:00:00', 400, 300));
const november = [4, 5].map((id) => makeAsset(id, '2020-11-01T00:00:00', 300, 400));

describe('monthLayouts', () => {
	it('lays out each month as justify does, in order', () => {
		const layouts = monthLayouts()(groupByMonth([...december, ...november]), 600, 150, 3);
		expect(layouts).toEqual([
			justify(december.map(aspect), 600, 150, 3),
			justify(november.map(aspect), 600, 150, 3)
		]);
	});

	it('no months: no layouts', () => {
		expect(monthLayouts()([], 600, 150, 3)).toEqual([]);
	});

	it('a new page keeps the layout of the months it did not touch', () => {
		const layoutsFor = monthLayouts();
		const [first] = layoutsFor(groupByMonth(december), 600, 150, 3);
		const [again, added] = layoutsFor(groupByMonth([...december, ...november]), 600, 150, 3);
		expect(again).toBe(first);
		expect(added.boxes).toHaveLength(2);
	});

	it('a month that got more photos is laid out anew', () => {
		const layoutsFor = monthLayouts();
		const [before] = layoutsFor(groupByMonth(december.slice(0, 2)), 600, 150, 3);
		const [after] = layoutsFor(groupByMonth(december), 600, 150, 3);
		expect(after).not.toBe(before);
		expect(after.boxes).toHaveLength(3);
	});

	it('a photo that changed shape (a rotation) lays its month out anew', () => {
		const layoutsFor = monthLayouts();
		const [before] = layoutsFor(groupByMonth(december), 600, 150, 3);
		const turned = [makeAsset(1, '2020-12-01T00:00:00', 300, 400), ...december.slice(1)];
		const [after] = layoutsFor(groupByMonth(turned), 600, 150, 3);
		expect(after).not.toBe(before);
		expect(after).toEqual(justify(turned.map(aspect), 600, 150, 3));
	});

	it.each([
		['width', [700, 150, 3]],
		['row height', [600, 200, 3]],
		['gap', [600, 150, 6]]
	] as const)('another %s lays everything out anew', (_, [width, rowHeight, gap]) => {
		const layoutsFor = monthLayouts();
		const [before] = layoutsFor(groupByMonth(december), 600, 150, 3);
		const [after] = layoutsFor(groupByMonth(december), width, rowHeight, gap);
		expect(after).not.toBe(before);
		expect(after).toEqual(justify(december.map(aspect), width, rowHeight, gap));
	});

	it('forgets a month that was not asked for the last time', () => {
		const layoutsFor = monthLayouts();
		const [first] = layoutsFor(groupByMonth(december), 600, 150, 3);
		layoutsFor(groupByMonth(november), 600, 150, 3);
		const [later] = layoutsFor(groupByMonth(december), 600, 150, 3);
		expect(later).not.toBe(first);
		expect(later).toEqual(first);
	});

	it('two timelines do not share what they remember', () => {
		const [one] = monthLayouts()(groupByMonth(december), 600, 150, 3);
		const [other] = monthLayouts()(groupByMonth(december), 600, 150, 3);
		expect(other).not.toBe(one);
	});
});
