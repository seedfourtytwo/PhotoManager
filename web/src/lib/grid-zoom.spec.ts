import { describe, expect, it } from 'vitest';
import {
	LEVELS,
	Pinch,
	defaultLevel,
	deviceOf,
	keyStep,
	loadLevel,
	pinchStep,
	rowHeightAt,
	saveLevel,
	stepLevel,
	wheelStep
} from './grid-zoom';
import { rowHeightFor } from './timeline';

/** A stand-in for localStorage. */
function memory(seed: Record<string, string> = {}) {
	const data = new Map(Object.entries(seed));
	return {
		getItem: (key: string) => data.get(key) ?? null,
		setItem: (key: string, value: string) => void data.set(key, value),
		data
	};
}

describe('levels', () => {
	it('five row heights per device, smallest first', () => {
		expect(LEVELS.phone).toEqual([60, 84, 110, 160, 240]);
		expect(LEVELS.laptop).toEqual([120, 160, 220, 300, 420]);
	});

	it('a phone is narrower than 640 px; everything wider zooms as a laptop', () => {
		expect(deviceOf(390)).toBe('phone');
		expect(deviceOf(639)).toBe('phone');
		expect(deviceOf(640)).toBe('laptop');
		expect(deviceOf(1440)).toBe('laptop');
	});

	it('the look’s photo size picks where a device starts, near the sizes it had', () => {
		expect(defaultLevel('small')).toBe(1);
		expect(defaultLevel('medium')).toBe(2);
		expect(defaultLevel('large')).toBe(3);
		for (const size of ['small', 'medium', 'large'] as const) {
			for (const width of [390, 1440]) {
				const level = rowHeightAt(deviceOf(width), defaultLevel(size));
				expect(Math.abs(level - rowHeightFor(width, size))).toBeLessThanOrEqual(10);
			}
		}
	});

	it('steps one level at a time and stops at either end', () => {
		expect(stepLevel(2, 1)).toBe(3);
		expect(stepLevel(2, -1)).toBe(1);
		expect(stepLevel(4, 1)).toBe(4);
		expect(stepLevel(0, -1)).toBe(0);
	});

	it('a row height for a level out of range is the nearest end', () => {
		expect(rowHeightAt('phone', 9)).toBe(240);
		expect(rowHeightAt('laptop', -3)).toBe(120);
	});
});

describe('gestures', () => {
	it('two fingers apart past 1.15 × zoom in; together past 0.87 × zoom out', () => {
		expect(pinchStep(1.16)).toBe(1);
		expect(pinchStep(1.15)).toBe(0);
		expect(pinchStep(1)).toBe(0);
		expect(pinchStep(0.87)).toBe(0);
		expect(pinchStep(0.86)).toBe(-1);
	});

	it('⌘ or Ctrl with + (or =) and − zoom; the bare keys do nothing', () => {
		const key = (k: string, mods: { metaKey?: boolean; ctrlKey?: boolean } = {}) =>
			keyStep({ key: k, metaKey: false, ctrlKey: false, ...mods });
		expect(key('=', { metaKey: true })).toBe(1);
		expect(key('+', { ctrlKey: true })).toBe(1);
		expect(key('-', { metaKey: true })).toBe(-1);
		expect(key('-')).toBe(0);
		expect(key('=')).toBe(0);
		expect(key('a', { metaKey: true })).toBe(0);
	});

	it('a trackpad pinch (a wheel with Ctrl) zooms once it has gone far enough', () => {
		expect(wheelStep(0, { ctrlKey: true, deltaY: -10 })).toEqual({ step: 0, sum: -10 });
		expect(wheelStep(-10, { ctrlKey: true, deltaY: -40 })).toEqual({ step: 1, sum: 0 });
		expect(wheelStep(0, { ctrlKey: true, deltaY: 60 })).toEqual({ step: -1, sum: 0 });
		// A plain wheel scrolls the page: nothing to count.
		expect(wheelStep(30, { ctrlKey: false, deltaY: 60 })).toEqual({ step: 0, sum: 0 });
	});
});

describe('Pinch', () => {
	it('one finger is no pinch', () => {
		const pinch = new Pinch();
		pinch.down(1, 100, 100);
		expect(pinch.move(1, 200, 300)).toBeNull();
		expect(pinch.active).toBe(false);
	});

	it('two fingers spreading step once past the threshold, then count again from there', () => {
		const pinch = new Pinch();
		pinch.down(1, 100, 100);
		pinch.down(2, 200, 100); // 100 px apart
		expect(pinch.active).toBe(true);
		expect(pinch.move(2, 210, 100)).toEqual({ step: 0, x: 155, y: 100 });
		expect(pinch.move(2, 220, 100)).toEqual({ step: 1, x: 160, y: 100 }); // 120 px: 1.2 ×
		// From 120 px now: 130 is not yet another step, 140 is.
		expect(pinch.move(2, 230, 100)?.step).toBe(0);
		expect(pinch.move(2, 240, 100)?.step).toBe(1);
	});

	it('two fingers closing step out', () => {
		const pinch = new Pinch();
		pinch.down(1, 0, 0);
		pinch.down(2, 0, 200);
		expect(pinch.move(1, 0, 40)?.step).toBe(-1); // 160 px: 0.8 ×
	});

	it('a finger lifted ends the pinch; a third one is ignored', () => {
		const pinch = new Pinch();
		pinch.down(1, 0, 0);
		pinch.down(2, 100, 0);
		pinch.down(3, 50, 50);
		expect(pinch.move(3, 500, 500)).toBeNull();
		pinch.up(2);
		expect(pinch.active).toBe(false);
		expect(pinch.move(1, 10, 10)).toBeNull();
	});
});

describe('remembered per device', () => {
	it('saves and loads a level for each device on its own', () => {
		const storage = memory();
		saveLevel(storage, 'phone', 4);
		expect(loadLevel(storage, 'phone')).toBe(4);
		expect(loadLevel(storage, 'laptop')).toBeNull();
		saveLevel(storage, 'laptop', 0);
		expect(loadLevel(storage, 'laptop')).toBe(0);
		expect(loadLevel(storage, 'phone')).toBe(4);
	});

	it('ignores what it cannot read: nothing saved, a wrong value, a storage that throws', () => {
		expect(loadLevel(memory({ 'grid-zoom': 'not json' }), 'phone')).toBeNull();
		expect(loadLevel(memory({ 'grid-zoom': '{"phone":7}' }), 'phone')).toBeNull();
		expect(loadLevel(memory({ 'grid-zoom': '{"phone":1.5}' }), 'phone')).toBeNull();
		const broken = {
			getItem: () => {
				throw new Error('blocked');
			},
			setItem: () => {
				throw new Error('blocked');
			}
		};
		expect(loadLevel(broken, 'phone')).toBeNull();
		expect(() => saveLevel(broken, 'phone', 2)).not.toThrow();
	});
});
