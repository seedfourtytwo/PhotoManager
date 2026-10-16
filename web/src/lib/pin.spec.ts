import { describe, expect, it } from 'vitest';
import { PAD_KEYS, enterPin, refusePin, pressKey, startPin } from './pin';

describe('a new PIN is asked for twice', () => {
	it('change PIN: current, then new, then the new one again', () => {
		let flow = startPin(true);
		expect(flow.step).toBe('current');
		({ flow } = enterPin(flow, '1111'));
		expect(flow.step).toBe('new');
		({ flow } = enterPin(flow, '2222'));
		expect(flow.step).toBe('again');
		const end = enterPin(flow, '2222');
		expect(end.done).toEqual({ current: '1111', pin: '2222' });
	});

	it('nothing is done before the second entry', () => {
		let flow = startPin(true);
		for (const pin of ['1111', '2222']) {
			const step = enterPin(flow, pin);
			expect(step.done).toBeNull();
			flow = step.flow;
		}
	});

	it('two different entries start the new PIN over, and say so', () => {
		let flow = startPin(true);
		({ flow } = enterPin(flow, '1111'));
		({ flow } = enterPin(flow, '2222'));
		const wrong = enterPin(flow, '2223');
		expect(wrong.done).toBeNull();
		expect(wrong.flow.step).toBe('new');
		expect(wrong.flow.error).toBe("Those didn't match. Try again.");
		// the current PIN is kept: only the new one is asked again
		({ flow } = enterPin(wrong.flow, '3333'));
		expect(flow.error).toBe('');
		expect(enterPin(flow, '3333').done).toEqual({ current: '1111', pin: '3333' });
	});

	it('reset and setup have no current PIN to ask for', () => {
		let flow = startPin(false);
		expect(flow.step).toBe('new');
		({ flow } = enterPin(flow, '4321'));
		expect(enterPin(flow, '4321').done).toEqual({ current: '', pin: '4321' });
	});

	it('anything but four digits is not taken', () => {
		const flow = startPin(false);
		expect(enterPin(flow, '12').flow).toBe(flow);
		expect(enterPin(flow, '12a4').flow).toBe(flow);
	});

	it('a refusal from the server starts over at the first step with its reason', () => {
		let flow = startPin(true);
		for (const pin of ['1111', '2222']) ({ flow } = enterPin(flow, pin));
		const again = refusePin(flow, 'The current PIN is wrong.');
		expect(again).toMatchObject({
			step: 'current',
			current: '',
			next: '',
			error: 'The current PIN is wrong.'
		});
	});
});

describe('number pad', () => {
	it('lays its keys out as a phone does: 1 to 9, then 0 with Delete to its right', () => {
		expect(PAD_KEYS).toEqual(['1', '2', '3', '4', '5', '6', '7', '8', '9', null, '0', 'delete']);
	});
	it('a digit joins the end', () => {
		expect(pressKey('', '1')).toBe('1');
		expect(pressKey('12', '0')).toBe('120');
	});
	it('a fifth digit is not taken: a PIN has four', () => {
		expect(pressKey('1234', '5')).toBe('1234');
	});
	it('Delete takes the last digit back, and nothing from nothing', () => {
		expect(pressKey('123', 'delete')).toBe('12');
		expect(pressKey('', 'delete')).toBe('');
	});
});
