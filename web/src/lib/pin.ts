import { PIN_LENGTH } from '$lib/api';

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
