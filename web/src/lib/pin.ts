import { PIN_LENGTH } from '$lib/api';

/** Attributes every PIN field shares: hidden digits, the phone's number pad, four at most.
 *  No `pattern`: the browser's own bubble would hide the sentence each form shows instead. */
export const PIN_FIELD = {
	type: 'password',
	inputmode: 'numeric',
	maxlength: PIN_LENGTH
} as const;
