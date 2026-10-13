/** "Send to a device": the words of the dialog and of the trail (no state, no requests). */
import type { Handover, HandoverOptions, LinkAddress } from './api/types';
import { formatBytes, formatWhen, photos } from './format';

/** The warning a sender reads before every link that is not https. */
export const UNENCRYPTED_WARNING =
	'Anyone on the same network could see these photos while they travel. Fine for something ' +
	'unimportant, not for anything private.';

const hostOf = (origin: string) => origin.replace(/^https?:\/\//, '');

/** The choice shown when a link can point to more than one address. */
export function addressLabel(address: LinkAddress): string {
	const where =
		address.via === 'home' ? 'On the home Wi-Fi' : 'Somewhere that reaches this address';
	return `${where} · ${address.encrypted ? 'encrypted' : 'not encrypted'} (${hostOf(address.origin)})`;
}

/** The address to start on: an encrypted one if there is one, else the first. */
export function firstChoice(addresses: LinkAddress[]): LinkAddress | null {
	return addresses.find((a) => a.encrypted) ?? addresses[0] ?? null;
}

/**
 * Why nothing can be sent, in one sentence that says what to do, or null when it can.
 * An admin is told the setting; anyone else is told whom to ask.
 */
export function unavailable(
	options: HandoverOptions,
	chosen: LinkAddress | null,
	admin: boolean
): string | null {
	if (!chosen)
		return admin
			? 'Other devices cannot open the address you are using. Set one they can reach on the ' +
					'server (PA_SEND_TO_DEVICE_ADDRESS, see the guide "Send to a device"), or open the ' +
					'library at its Tailscale address.'
			: 'Other devices cannot open the address you are using. Open the library at its usual ' +
					'address and try again, or ask whoever runs the library.';
	if (!chosen.encrypted && !options.unencrypted_allowed)
		return (
			'Sending without encryption is switched off here. Open the library at its https ' +
			'address and send from there.'
		);
	return null;
}

/** "3 photos · 8.4 MB · details removed" */
export function summary(handover: Pick<Handover, 'count' | 'bytes' | 'details_removed'>): string {
	const details = handover.details_removed ? 'details removed' : 'details kept';
	return `${photos(handover.count)} · ${formatBytes(handover.bytes)} · ${details}`;
}

/** "9:41" for the countdown; "0:00" once the time is over. */
export function clock(ms: number): string {
	const seconds = Math.max(0, Math.ceil(ms / 1000));
	return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

/** The live line under the code. */
export function stateLine(state: Handover['state']): string {
	return {
		waiting: 'Waiting for the other device…',
		redeemed: 'Downloaded on another device.',
		expired: 'This link has run out. Nothing was downloaded.',
		cancelled: 'This link was cancelled.'
	}[state];
}

/** What kind of device a browser says it is, for the trail: a word, not the whole string. */
export function deviceWord(agent: string | null): string {
	if (!agent) return 'a device';
	const known: [RegExp, string][] = [
		[/iPhone/, 'an iPhone'],
		[/iPad/, 'an iPad'],
		[/Android/, 'an Android device'],
		[/Macintosh|Mac OS X/, 'a Mac'],
		[/Windows/, 'a Windows computer'],
		[/Linux|X11/, 'a Linux computer']
	];
	return known.find(([pattern]) => pattern.test(agent))?.[1] ?? 'a device';
}

/** What became of a link, for the trail: "Downloaded 13 Oct 2026, 14:02 by an iPhone at 100.64.0.9". */
export function outcome(handover: Handover): string {
	if (handover.state === 'redeemed') {
		const who = deviceWord(handover.redeemed_agent);
		const from = handover.redeemed_from ? ` at ${handover.redeemed_from}` : '';
		return `Downloaded ${formatWhen(handover.redeemed_at)} by ${who}${from}`;
	}
	return {
		waiting: `Waiting until ${formatWhen(handover.expires_at)}`,
		expired: 'Ran out, never downloaded',
		cancelled: 'Cancelled'
	}[handover.state];
}
