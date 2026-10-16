import { tick } from 'svelte';
import { page, userEvent } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import SortableList from './SortableList.svelte';

type Row = 'people' | 'places' | 'albums' | 'utilities';
const ALL: readonly Row[] = ['people', 'places', 'albums', 'utilities'];
const NAMES = { people: 'People', places: 'Places', albums: 'Albums', utilities: 'Utilities' };
const LABEL = 'Collections shows, in this order';
const group = () => page.getByRole('group', { name: LABEL });
/** What the list says aloud as a row moves. */
const said = () => page.elementLocator(document.querySelector('.sortable .said')!);

/** The list as a parent keeps it: each change is saved and given back, as Settings does. */
function show(chosen: Row[], extra: { hints?: Partial<Record<Row, string>> } = {}) {
	const onchange = vi.fn<(next: Row[]) => void>();
	const view = render(SortableList, {
		label: LABEL,
		all: ALL,
		chosen,
		names: NAMES,
		onchange: (next: string[]) => {
			onchange(next as Row[]);
			void view.rerender({ chosen: next as Row[] });
		},
		...extra
	});
	return onchange;
}

const row = (name: string) =>
	document.querySelector<HTMLElement>(`li[data-key="${name.toLowerCase()}"]`)!;
const middle = (el: HTMLElement) => {
	const box = el.getBoundingClientRect();
	return { x: box.left + box.width / 2, y: box.top + box.height / 2 };
};
function finger(target: HTMLElement, type: string, y: number, pointerType = 'mouse') {
	target.dispatchEvent(
		new PointerEvent(type, {
			bubbles: true,
			cancelable: true,
			pointerId: 9,
			pointerType,
			isPrimary: true,
			button: 0,
			clientX: middle(target).x,
			clientY: y
		})
	);
}
const frames = (n = 2) =>
	new Promise<void>((done) => {
		const next = (left: number) => (left ? requestAnimationFrame(() => next(left - 1)) : done());
		next(n);
	});

describe('SortableList: some of a list, switched on and put in order', () => {
	it('lists the shown in their order, then the others, switched off', async () => {
		show(['albums', 'people']);
		const switches = group().getByRole('switch');
		await expect.element(switches.nth(0)).toHaveAccessibleName('Albums');
		await expect.element(switches.nth(1)).toHaveAccessibleName('People');
		await expect.element(switches.nth(2)).toHaveAccessibleName('Places');
		await expect.element(switches.nth(3)).toHaveAccessibleName('Utilities');
		await expect.element(switches.nth(0)).toBeChecked();
		await expect.element(switches.nth(2)).not.toBeChecked();
		await expect.element(group().getByRole('list', { name: 'Shown', exact: true })).toBeVisible();
		await expect.element(group().getByRole('list', { name: 'Not shown' })).toBeVisible();
	});

	it('a switch turned on puts it last of the shown; turned off takes it out', async () => {
		const onchange = show(['albums', 'people']);
		await userEvent.click(group().getByRole('switch', { name: 'Places' }));
		expect(onchange).toHaveBeenLastCalledWith(['albums', 'people', 'places']);
		await userEvent.click(group().getByRole('switch', { name: 'Albums' }));
		expect(onchange).toHaveBeenLastCalledWith(['people', 'places']);
	});

	it('never lets the last one shown be turned off', async () => {
		show(['places']);
		await expect.element(group().getByRole('switch', { name: 'Places' })).toBeDisabled();
		await expect.element(group().getByRole('switch', { name: 'People' })).toBeEnabled();
	});

	it('a quiet hint says a row has nothing to show today', async () => {
		show(['albums', 'people'], { hints: { people: 'Nothing today' } });
		await expect.element(page.getByText('Nothing today')).toBeVisible();
	});

	it('only the shown rows have a grip, named for the row', async () => {
		show(['albums', 'people']);
		await expect.element(group().getByRole('button', { name: 'Reorder Albums' })).toBeVisible();
		await expect
			.element(group().getByRole('button', { name: 'Reorder Places' }))
			.not.toBeInTheDocument();
	});
});

describe('SortableList: Move up and Move down, for a screen reader', () => {
	it('each shown row has them where they lead somewhere; they move it one place', async () => {
		const onchange = show(['albums', 'people', 'places']);
		const button = (name: string) => group().getByRole('button', { name, exact: true });
		await expect.element(button('Move Albums up')).not.toBeInTheDocument();
		await expect.element(button('Move Places down')).not.toBeInTheDocument();
		await expect.element(button('Move Utilities up')).not.toBeInTheDocument();
		(button('Move People up').element() as HTMLElement).click();
		expect(onchange).toHaveBeenLastCalledWith(['people', 'albums', 'places']);
		await tick();
		(button('Move People down').element() as HTMLElement).click();
		expect(onchange).toHaveBeenLastCalledWith(['albums', 'people', 'places']);
	});

	it('are hidden until focused, then show', async () => {
		show(['albums', 'people']);
		const move = group().getByRole('button', { name: 'Move People up' }).element() as HTMLElement;
		expect(move.getBoundingClientRect().width).toBeLessThanOrEqual(1);
		move.focus();
		await tick();
		expect(move.getBoundingClientRect().width).toBeGreaterThan(20);
	});
});

describe('SortableList: the keyboard on the grip', () => {
	it('Space picks up, the arrows move, Space drops: saved once, where it was dropped', async () => {
		const onchange = show(['albums', 'people', 'places']);
		const grip = group().getByRole('button', { name: 'Reorder Places' });
		(grip.element() as HTMLElement).focus();
		await userEvent.keyboard(' ');
		await expect.element(said()).toHaveTextContent('Places picked up, 3 of 3');
		await userEvent.keyboard('{ArrowUp}');
		await expect.element(said()).toHaveTextContent('Places, 2 of 3');
		await userEvent.keyboard('{ArrowUp}');
		await userEvent.keyboard('{ArrowUp}'); // already first: stays
		await expect.element(said()).toHaveTextContent('Places, 1 of 3');
		expect(onchange).not.toHaveBeenCalled();
		// the grip keeps the focus as its row moves
		expect(document.activeElement).toBe(grip.element());
		await userEvent.keyboard(' ');
		expect(onchange).toHaveBeenCalledTimes(1);
		expect(onchange).toHaveBeenLastCalledWith(['places', 'albums', 'people']);
		await expect.element(said()).toHaveTextContent('Places dropped, 1 of 3');
	});

	it('Escape puts it back where it was, and nothing is saved', async () => {
		const onchange = show(['albums', 'people', 'places']);
		const grip = group().getByRole('button', { name: 'Reorder Places' });
		(grip.element() as HTMLElement).focus();
		await userEvent.keyboard(' ');
		await userEvent.keyboard('{ArrowUp}');
		await userEvent.keyboard('{Escape}');
		expect(onchange).not.toHaveBeenCalled();
		const switches = group().getByRole('switch');
		await expect.element(switches.nth(2)).toHaveAccessibleName('Places');
	});
});

describe('SortableList: the finger', () => {
	it('the grip drags a row at once; the others step aside; let go, it is saved there', async () => {
		const onchange = show(['albums', 'people', 'places']);
		const grip = row('places').querySelector<HTMLElement>('.grip')!;
		const from = middle(grip).y;
		const first = middle(row('albums')).y;
		finger(grip, 'pointerdown', from);
		finger(grip, 'pointermove', from - 20);
		finger(grip, 'pointermove', first - 10);
		await tick();
		expect(row('places').classList.contains('lifted')).toBe(true);
		expect(row('albums').style.transform).toMatch(/translateY\(\d/);
		finger(grip, 'pointerup', first - 10);
		expect(onchange).toHaveBeenLastCalledWith(['places', 'albums', 'people']);
	});

	it('let go, the row springs into its slot (transform only) and comes to rest', async () => {
		show(['albums', 'people', 'places']);
		const grip = row('places').querySelector<HTMLElement>('.grip')!;
		const from = middle(grip).y;
		finger(grip, 'pointerdown', from);
		finger(grip, 'pointermove', middle(row('albums')).y - 10);
		finger(grip, 'pointerup', middle(row('albums')).y - 10);
		await tick();
		await frames(2);
		// on its way: it starts from where the finger left it
		expect(row('places').style.transform).toMatch(/translateY\(-?[\d.]+px\)/);
		await expect.poll(() => row('places').style.transform, { timeout: 3000 }).toBe('');
		expect(row('places').classList.contains('lifted')).toBe(false);
	});

	it('dropped where it was, nothing is saved and every row comes home', async () => {
		const onchange = show(['albums', 'people', 'places']);
		const grip = row('people').querySelector<HTMLElement>('.grip')!;
		const from = middle(grip).y;
		finger(grip, 'pointerdown', from);
		finger(grip, 'pointermove', from + 10);
		finger(grip, 'pointerup', from + 10);
		expect(onchange).not.toHaveBeenCalled();
		await expect.poll(() => row('people').style.transform, { timeout: 3000 }).toBe('');
	});

	it('a touch held still on a shown row picks it up; a touch that moves first is a scroll', async () => {
		const onchange = show(['albums', 'people', 'places']);
		const target = row('places').querySelector<HTMLElement>('.row-name')!;
		const from = middle(row('places')).y;
		// moved before the hold: nothing lifts
		finger(target, 'pointerdown', from, 'touch');
		finger(target, 'pointermove', from - 30, 'touch');
		await new Promise((done) => setTimeout(done, 400));
		expect(row('places').classList.contains('lifted')).toBe(false);
		finger(target, 'pointerup', from - 30, 'touch');

		finger(target, 'pointerdown', from, 'touch');
		await new Promise((done) => setTimeout(done, 400));
		await tick();
		expect(row('places').classList.contains('lifted')).toBe(true);
		const top = middle(row('albums')).y - 10;
		finger(target, 'pointermove', top, 'touch');
		finger(target, 'pointerup', top, 'touch');
		expect(onchange).toHaveBeenLastCalledWith(['places', 'albums', 'people']);
	});
});
