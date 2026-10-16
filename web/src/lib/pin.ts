import { PIN_LENGTH, isPin } from '$lib/api';

/**
 * Setting a PIN, one entry at a time (spec flight/admin-settings-auth §4): the current one
 * when changing your own, then the new one twice, so a typo can't lock anyone out.
 */
export type PinStep = 'current' | 'new' | 'again';
export type PinFlow = { step: PinStep; current: string; next: string; error: string };
/** What the keypad's heading says at each step. */
export const PIN_PROMPTS: Record<PinStep, string> = {
	current: 'Current PIN',
	new: 'New PIN',
	again: 'New PIN again'
};
export const PIN_MISMATCH = "Those didn't match. Try again.";

export function startPin(askCurrent: boolean): PinFlow {
	return { step: askCurrent ? 'current' : 'new', current: '', next: '', error: '' };
}

/** One whole entry: the next step, or `done` once the new PIN was given the same twice. */
export function enterPin(
	flow: PinFlow,
	pin: string
): { flow: PinFlow; done: { current: string; pin: string } | null } {
	if (!isPin(pin)) return { flow, done: null };
	if (flow.step === 'current') return { flow: { ...flow, step: 'new', current: pin, error: '' }, done: null };
	if (flow.step === 'new') return { flow: { ...flow, step: 'again', next: pin, error: '' }, done: null };
	if (pin !== flow.next) return { flow: { ...flow, step: 'new', next: '', error: PIN_MISMATCH }, done: null };
	return { flow, done: { current: flow.current, pin } };
} // prettier-ignore

/** The server said no (the current PIN was wrong, say): start again, with its reason. */
export function refusePin(flow: PinFlow, error: string): PinFlow {
	return { ...startPin(flow.current !== ''), error };
}

/** Attributes every PIN field shares: hidden digits, the phone's number pad, four at most.
 *  No `pattern`: the browser's own bubble would hide the sentence each form shows instead. */
export const PIN_FIELD = {
	type: 'password',
	inputmode: 'numeric',
	maxlength: PIN_LENGTH
} as const;

/** The keys of the sign-in pad, row by row as on a phone; null is the empty place left of 0. */
export const PAD_KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', null, '0', 'delete'] as const;
export type PadKey = Exclude<(typeof PAD_KEYS)[number], null>;

/** The PIN after one press: a digit joins the end (four at most), Delete takes the last back. */
export function pressKey(pin: string, key: PadKey): string {
	if (key === 'delete') return pin.slice(0, -1);
	return pin.length < PIN_LENGTH ? pin + key : pin;
}
